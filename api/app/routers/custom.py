from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_serializer
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..models import User, UserPreference
from ..db_tools.shared_sql import get_exchange_rate_by_as_of

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


def get_user_pref(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserPreference:
    pref = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not pref:
        raise HTTPException(status_code=404, detail="user_pref_not_found")
    return pref


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
    
class AssetCurrencyPoint(BaseModel):
    amount: Decimal
    change: Decimal
    rate: Decimal
    target: str
    
    @field_serializer("amount")
    def serialize_amount(self, v: Decimal):
        return float(v)
    
    @field_serializer("change")
    def serialize_change(self, v: Decimal):
        return float(v)
    
    @field_serializer("rate")
    def serialize_rate(self, v: Decimal):
        return float(v)
    
class AssetCurrencyTotalOut(BaseModel):
    data: List[AssetCurrencyPoint]
    
class ExpensePeriodCompareOut(BaseModel):
    currency: str
    current_from: datetime
    current_to: datetime
    current_total: Decimal
    previous_from: datetime
    previous_to: datetime
    previous_total: Decimal
    delta: Decimal
    delta_rate: Decimal

@router.get("/institutions/assets/changes", response_model=InstitutionAssetChangeOut)
def list_institution_asset_changes(
    limit: int = Query(10, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pref: UserPreference = Depends(get_user_pref),
):
    base_currency = pref.base_currency

    sql = text(
        """
        WITH balance_ranked AS (
          SELECT
            i.id AS institution_id,
            i.name AS institution_name,
            i.type AS institution_type,
            pb.as_of,
            pb.amount,
            fp.currency,
            DENSE_RANK() OVER (ORDER BY pb.as_of DESC) AS rnk,
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
        balance_fx AS (
          SELECT
            institution_id,
            institution_name,
            institution_type,
            as_of,
            amount,
            fx_rate
          FROM balance_ranked
          WHERE rnk <= 2
          ORDER BY as_of DESC
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
        """
    )
    rows = db.execute(
        sql,
        {"user_id": current_user.id, "target_code": base_currency, "limit": limit},
    ).mappings()
    rows = list(rows)
    limit = min(limit, len(rows))
    head_count = (limit + 1) // 2   # 前半：向上取整
    tail_count = limit // 2         # 后半：向下取整
    head = rows[:head_count]
    tail = rows[-tail_count:]
    rows = head + tail
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
    pref: UserPreference = Depends(get_user_pref),
):
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
    pref: UserPreference = Depends(get_user_pref),
):
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
    
@router.get("/total/products/compare", response_model=AssetCurrencyTotalOut)
def get_total_assets_by_currency(
    key: str = Query("currency", regex="^(currency|product_type)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pref: UserPreference = Depends(get_user_pref),
):
    base_currency = pref.base_currency

    sql = text(
        f"""
        WITH balance_fx AS (
          SELECT
            fp.id,
            fp.{key} AS target,
            pb.as_of,
            pb.amount,
            DENSE_RANK() OVER (ORDER BY pb.as_of DESC) AS rnk,
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="fp",
            column="fx_rate",
            currency="fp",
            as_of_column="amount_updated_at",
        )
        + """
          FROM deposit.product_balances pb
          JOIN deposit.financial_products fp ON fp.id = pb.product_id
          JOIN deposit.institutions i ON i.id = fp.institution_id
          WHERE i.user_id = :user_id
            AND fp.status != 'closed'
        )
        SELECT
          SUM(amount * fx_rate) AS total,
          as_of,
          target
        FROM balance_fx
        WHERE fx_rate IS NOT NULL
          AND rnk <= 2
        GROUP BY as_of, target
        ORDER BY as_of DESC
        """
    )
    rows = list(db.execute(
        sql,
        {
            "user_id": current_user.id,
            "target_code": base_currency,
        },
    ).mappings())
    results: List[AssetCurrencyPoint] = [] 
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["target"]].append(row)
    for target, rows in grouped.items():
        change = rows[0]["total"] - rows[1]["total"] if len(rows) > 1 else 0
        rate = change / rows[0]["total"] if len(rows) > 1 else 1
        results.append(AssetCurrencyPoint(
            target=target,
            amount=rows[0]["total"],
            change=change,
            rate=rate,
        ))
    return AssetCurrencyTotalOut(
        data=results
    ).model_dump()


@router.get("/expenses/total/compare", response_model=ExpensePeriodCompareOut)
def get_expense_total_compare(
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    pref: UserPreference = Depends(get_user_pref),
):
    if not from_dt or not to_dt:
        raise HTTPException(status_code=422, detail="missing_time_range")
    if from_dt >= to_dt:
        raise HTTPException(status_code=422, detail="invalid_time_range")

    duration = to_dt - from_dt
    prev_from = from_dt - duration
    prev_to = from_dt

    base_currency = pref.base_currency

    sql = text(
        """
        WITH current_fx AS (
          SELECT
            e.amount,
            e.currency,
            e.occurred_at,
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="e",
            column="fx_rate",
            currency="e",
            as_of_column="occurred_at",
        )
        + """
          FROM expense.expenses e
          WHERE e.user_id = :user_id
            AND e.occurred_at >= :from_dt
            AND e.occurred_at < :to_dt
        ),
        current_total AS (
          SELECT COALESCE(SUM(amount * fx_rate), 0) AS total
          FROM current_fx
          WHERE fx_rate IS NOT NULL
        ),
        previous_fx AS (
          SELECT
            e.amount,
            e.currency,
            e.occurred_at,
        """
        + get_exchange_rate_by_as_of(
            code=":target_code",
            as_of="e",
            column="fx_rate",
            currency="e",
            as_of_column="occurred_at",
        )
        + """
          FROM expense.expenses e
          WHERE e.user_id = :user_id
            AND e.occurred_at >= :prev_from
            AND e.occurred_at < :prev_to
        ),
        previous_total AS (
          SELECT COALESCE(SUM(amount * fx_rate), 0) AS total
          FROM previous_fx
          WHERE fx_rate IS NOT NULL
        )
        SELECT
          current_total.total AS current_total,
          previous_total.total AS previous_total
        FROM current_total
        CROSS JOIN previous_total
        """
    )
    row = db.execute(
        sql,
        {
            "user_id": current_user.id,
            "from_dt": from_dt,
            "to_dt": to_dt,
            "prev_from": prev_from,
            "prev_to": prev_to,
            "target_code": base_currency,
        },
    ).mappings().first()

    current_total = row["current_total"] if row else Decimal("0")
    previous_total = row["previous_total"] if row else Decimal("0")
    delta = current_total - previous_total
    delta_rate = delta / previous_total if previous_total else Decimal("0")

    return ExpensePeriodCompareOut(
        currency=base_currency,
        current_from=from_dt,
        current_to=to_dt,
        current_total=current_total,
        previous_from=prev_from,
        previous_to=prev_to,
        previous_total=previous_total,
        delta=delta,
        delta_rate=delta_rate,
    ).model_dump()
    
