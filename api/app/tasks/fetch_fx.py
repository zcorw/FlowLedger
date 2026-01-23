from __future__ import annotations

import os
import pathlib
import sys
from datetime import date as date_cls, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Tuple

import httpx
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

# Allow both `python -m app.tasks.fetch_fx` and `python api/app/tasks/fetch_fx.py`
if __package__ in (None, ""):
    ROOT = pathlib.Path(__file__).resolve().parents[2]
    sys.path.append(str(ROOT))
    from app.db import SessionLocal  # type: ignore
    from app.models import Currency, ExchangeRate, FinancialProduct  # type: ignore
else:
    from ..db import SessionLocal
    from ..models import Currency, ExchangeRate, FinancialProduct

load_dotenv()

# Configs with sensible defaults for a daily USD-based sync.
FX_BASE = os.getenv("FX_BASE", "USD").upper()
FX_TIMEOUT_MS = int(os.getenv("FX_TIMEOUT_MS", "5000"))
FX_TIMEOUT_SEC = float(os.getenv("FX_TIMEOUT_SECONDS", FX_TIMEOUT_MS / 1000))
FX_ENDPOINT_TEMPLATE = os.getenv(
    "FX_ENDPOINT_TEMPLATE",
    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base}.json",
)
FX_SOURCE = "fawazahmed0/exchange-api"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_rates(base: str) -> Tuple[date_cls, Dict[str, Decimal]]:
    """Fetch USD->others rates from fawazahmed0/exchange-api."""
    url = FX_ENDPOINT_TEMPLATE.format(base=base.lower())
    with httpx.Client(timeout=FX_TIMEOUT_SEC) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    date_str = payload.get("date")
    rate_date = date_cls.fromisoformat(date_str) if date_str else _now().date()
    raw_rates = payload.get(base.lower()) or {}

    parsed: Dict[str, Decimal] = {}
    for quote, rate in raw_rates.items():
        try:
            parsed[quote.upper()] = Decimal(str(rate))
        except (InvalidOperation, TypeError):
            continue
    return rate_date, parsed


def _load_currency_codes(db: Session) -> Iterable[str]:
    return db.scalars(select(Currency.code)).all()


def _load_asset_currency_codes(db: Session) -> list[str]:
    rows = (
        db.scalars(
            select(FinancialProduct.currency)
            .where(FinancialProduct.status == "active")
            .distinct()
        )
        .all()
    )
    return [row.upper() for row in rows if row]


def _upsert_rates(
    db: Session,
    *,
    base: str,
    rate_date: date_cls,
    rates: Dict[str, Decimal],
    target_quotes: Iterable[str],
) -> Dict[str, int]:
    now = _now()
    rows = []
    missing = 0

    for quote in target_quotes:
        if quote == base:
            continue
        rate = rates.get(quote)
        if rate is None:
            missing += 1
            continue
        rows.append(
            {
                "base_code": base,
                "quote_code": quote,
                "rate_date": rate_date,
                "rate": rate,
                "source": FX_SOURCE,
                "created_at": now,
                "updated_at": now,
            }
        )

    if not rows:
        return {"written": 0, "missing": missing}

    stmt = insert(ExchangeRate).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[ExchangeRate.base_code, ExchangeRate.quote_code, ExchangeRate.rate_date],
        set_={
            "rate": stmt.excluded.rate,
            "source": stmt.excluded.source,
            "updated_at": now,
        },
    )
    db.execute(stmt)
    db.commit()
    return {"written": len(rows), "missing": missing}


def sync_exchange_rates(db: Session, *, base: str | None = None) -> Dict[str, Any]:
    """Fetch and upsert rates for the given base (default FX_BASE)."""
    base_code = (base or FX_BASE).upper()
    codes = [c.upper() for c in _load_currency_codes(db)]
    if base_code not in codes:
        raise RuntimeError(f"Base currency {base_code} not found in currency.currencies")

    rate_date, rates = _fetch_rates(base_code)
    target_quotes = [c for c in codes if c != base_code]

    summary = _upsert_rates(
        db,
        base=base_code,
        rate_date=rate_date,
        rates=rates,
        target_quotes=target_quotes,
    )
    return {
        "base": base_code,
        "rate_date": rate_date.isoformat(),
        "written": summary["written"],
        "missing": summary["missing"],
    }


def sync_exchange_rates_for_assets(
    db: Session,
    *,
    target: str = "CNY",
) -> Dict[str, Any]:
    """Fetch and upsert FX rates from asset currencies to target currency."""
    target_code = target.upper()
    currency_codes = {c.upper() for c in _load_currency_codes(db)}
    if target_code not in currency_codes:
        raise RuntimeError(f"Target currency {target_code} not found in currency.currencies")

    asset_codes = {c.upper() for c in _load_asset_currency_codes(db)}
    asset_codes = {c for c in asset_codes if c in currency_codes}
    bases = sorted(asset_codes)
    results = []
    total_written = 0
    total_missing = 0

    for base_code in bases:
        if base_code == target_code:
            continue
        rate_date, rates = _fetch_rates(base_code)
        summary = _upsert_rates(
            db,
            base=base_code,
            rate_date=rate_date,
            rates=rates,
            target_quotes=[target_code],
        )
        results.append(
            {
                "base": base_code,
                "rate_date": rate_date.isoformat(),
                "written": summary["written"],
                "missing": summary["missing"],
            }
        )
        total_written += summary["written"]
        total_missing += summary["missing"]

    return {
        "target": target_code,
        "bases": bases,
        "written": total_written,
        "missing": total_missing,
        "results": results,
    }


def main() -> None:
    db = SessionLocal()
    try:
        summary = sync_exchange_rates_for_assets(db, target="CNY")
        print(
            f"[fx-sync] target={summary['target']} bases={len(summary['bases'])} "
            f"written={summary['written']} missing={summary['missing']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
