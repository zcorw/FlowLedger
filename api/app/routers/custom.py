from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..models import User, UserPreference

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
            CASE
              WHEN fp.currency = :target_code THEN 1::numeric
              ELSE COALESCE(
                (
                  SELECT er.rate
                  FROM currency.exchange_rates er
                  WHERE er.base_code = fp.currency
                    AND er.quote_code = :target_code
                    AND er.rate_date <= pb.as_of::date
                  ORDER BY er.rate_date DESC
                  LIMIT 1
                ),
                (
                  SELECT 1 / er2.rate
                  FROM currency.exchange_rates er2
                  WHERE er2.base_code = :target_code
                    AND er2.quote_code = fp.currency
                    AND er2.rate_date <= pb.as_of::date
                  ORDER BY er2.rate_date DESC
                  LIMIT 1
                )
              )
            END AS fx_rate
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
            as_of,
            SUM(amount * fx_rate) AS total_amount
          FROM balance_fx
          WHERE fx_rate IS NOT NULL
          GROUP BY institution_id, institution_name, institution_type, as_of
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
