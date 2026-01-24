from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..models import User, UserPreference
from app.db.shared_sql import get_exchange_rate_by_as_of

router = APIRouter(prefix="/v1/custom", tags=["custom"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


class InstitutionAssetChange(BaseModel):
    institution_id: int
    institution_name: str
    institution_type: str
    current_as_of: datetime
    previous_as_of: datetime
    current_total: Decimal
    previous_total: Decimal
    delta: Decimal


class InstitutionAssetChangeOut(BaseModel):
    currency: str
    total: int
    data: List[InstitutionAssetChange]


class MonthlyAssetPoint(BaseModel):
    month: date
    amount: Decimal


class MonthlyAssetTrend(BaseModel):
    currency: str
    data: List[MonthlyAssetPoint]


class LatestAumontTotalOut(BaseModel):
    currency: str
    datetime: datetime
    total: Decimal

@router.get("/institutions/assets/changes", response_model=InstitutionAssetChangeOut)
def list_institution_asset_changes(
    limit: int = Query(10, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="user_pref_not_found")
    base_currency = pref.base_currency

    sql = text(
        """
        WITH balance_fx AS (
          SELECT
            i.id AS institution_id,
            i.name AS institution_name,
            i.type AS institution_type,
            pb.as_of,
            pb.amount,
            fp.currency,
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="pb",
            column="fx_rate",
            currency="fp",
        )
        + """
          FROM deposit.product_balances pb
          JOIN deposit.financial_products fp ON fp.id = pb.product_id
          JOIN deposit.institutions i ON i.id = fp.institution_id
          WHERE i.user_id = :user_id
            AND fp.status != 'closed'
        ),
        institution_snapshots AS (
          SELECT
            institution_id,
            institution_name,
            institution_type,
            as_of::date AS as_of,
            SUM(amount * fx_rate) AS total_amount
          FROM balance_fx
          WHERE fx_rate IS NOT NULL
          GROUP BY institution_id, institution_name, institution_type, as_of::date
        ),
        ranked AS (
          SELECT
            institution_id,
            institution_name,
            institution_type,
            as_of,
            total_amount,
            row_number() OVER (PARTITION BY institution_id ORDER BY as_of DESC) AS rn
          FROM institution_snapshots
        ),
        pivot AS (
          SELECT
            institution_id,
            institution_name,
            institution_type,
            MAX(CASE WHEN rn = 1 THEN as_of END) AS current_as_of,
            MAX(CASE WHEN rn = 1 THEN total_amount END) AS current_total,
            MAX(CASE WHEN rn = 2 THEN as_of END) AS previous_as_of,
            MAX(CASE WHEN rn = 2 THEN total_amount END) AS previous_total
          FROM ranked
          WHERE rn <= 2
          GROUP BY institution_id, institution_name, institution_type
        )
        SELECT
          institution_id,
          institution_name,
          institution_type,
          current_as_of,
          previous_as_of,
          current_total,
          previous_total,
          (current_total - previous_total) AS delta
        FROM pivot
        WHERE previous_total IS NOT NULL
        ORDER BY delta DESC
        LIMIT :limit
        """
    )
    rows = db.execute(
        sql,
        {"user_id": current_user.id, "target_code": base_currency, "limit": limit},
    ).mappings()
    data = [
        InstitutionAssetChange(
            institution_id=row["institution_id"],
            institution_name=row["institution_name"],
            institution_type=row["institution_type"],
            current_as_of=row["current_as_of"],
            previous_as_of=row["previous_as_of"],
            current_total=row["current_total"],
            previous_total=row["previous_total"],
            delta=row["delta"],
        )
        for row in rows
    ]
    return InstitutionAssetChangeOut(
        currency=base_currency,
        total=len(data),
        data=data,
    ).model_dump()


@router.get("/assets/monthly", response_model=MonthlyAssetTrend)
def get_monthly_assets(
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    limit: Optional[int] = Query(None,ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="user_pref_not_found")
    base_currency = pref.base_currency

    sql = text(
        """
        WITH monthly_last AS (
          SELECT
            pb.product_id,
            fp.currency,
            date_trunc('month', pb.as_of)::date AS month_start,
            pb.as_of,
            pb.amount,
            row_number() OVER (
              PARTITION BY pb.product_id, date_trunc('month', pb.as_of)
              ORDER BY pb.as_of DESC
            ) AS rn
          FROM deposit.product_balances pb
          JOIN deposit.financial_products fp ON fp.id = pb.product_id
          JOIN deposit.institutions i ON i.id = fp.institution_id
          WHERE i.user_id = :user_id
            AND (:from_dt IS NULL OR pb.as_of >= :from_dt)
            AND (:to_dt IS NULL OR pb.as_of <= :to_dt)
            AND fp.status != 'closed'
        )
        SELECT
          m.month_start AS month,
          SUM(m.amount * fx.fx_rate) AS total_amount
        FROM monthly_last m
        LEFT JOIN LATERAL (
          SELECT
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="m",
            column="fx_rate",
            currency="m",
        )
        + """
        ) fx ON true
        WHERE m.rn = 1
          AND fx.fx_rate IS NOT NULL
        GROUP BY m.month_start
        ORDER BY m.month_start DESC
        LIMIT :limit
        """
    )
    rows = db.execute(
        sql,
        {
            "user_id": current_user.id,
            "from_dt": from_dt,
            "to_dt": to_dt,
            "target_code": base_currency,
            "limit": limit,
        },
    ).mappings()

    data = [
        MonthlyAssetPoint(month=row["month"], amount=row["total_amount"])
        for row in rows
    ]
    return MonthlyAssetTrend(currency=base_currency, data=data).model_dump()


@router.get("/total/assets/latest", response_model=LatestAumontTotalOut)
def get_latest_total_amount(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="user_pref_not_found")
    base_currency = pref.base_currency

    sql = text(
        """
        WITH balance_fx AS (
          SELECT
            i.id AS institution_id,
            i.name AS institution_name,
            fp.amount_updated_at::date AS as_of,
            fp.amount,
            fp.currency,
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="fp",
            column="fx_rate",
            currency="fp",
            as_of_column="amount_updated_at",
        )
        + """
          FROM deposit.financial_products fp
          JOIN deposit.institutions i ON i.id = fp.institution_id
          WHERE i.user_id = :user_id
            AND fp.status = 'active'
        )
        SELECT
          as_of,
          SUM(amount * fx_rate) AS total_amount
        FROM balance_fx
        WHERE fx_rate IS NOT NULL
        GROUP BY balance_fx.as_of
        ORDER BY balance_fx.as_of DESC
        LIMIT 1
        """
    )
    rows = list(db.execute(
        sql,
        {
            "user_id": current_user.id,
            "target_code": base_currency,
        },
    ).mappings())
    row = rows[0] if rows else None
    return LatestAumontTotalOut(
        currency=base_currency,
        datetime=row["as_of"],
        total=row["total_amount"],
    ).model_dump()
    
    
