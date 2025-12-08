from __future__ import annotations

from datetime import datetime, timezone, date as date_cls
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Currency, ExchangeRate


router = APIRouter(prefix="/v1", tags=["currency"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    symbol: Optional[str] = None
    scale: int


class PageOut(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
    items: List[CurrencyOut]


@router.get("/currencies", response_model=PageOut)
def list_currencies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    code: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = Query("code"),
    db: Session = Depends(get_db),
):
    query = db.query(Currency)
    if code:
        query = query.filter(Currency.code == code.upper())
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Currency.name.ilike(like), Currency.symbol.ilike(like)))

    # sorting
    if sort:
        for key in sort.split(","):
            key = key.strip()
            if not key:
                continue
            desc = key.startswith("-")
            field = key[1:] if desc else key
            col = getattr(Currency, field, None)
            if col is None:
                continue
            query = query.order_by(col.desc() if desc else col.asc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    items_out = [CurrencyOut.model_validate(it, from_attributes=True) for it in items]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "items": [it.model_dump() for it in items_out],
    }


@router.get("/currencies/{code}", response_model=CurrencyOut)
def get_currency(code: str, db: Session = Depends(get_db)):
    cur = db.get(Currency, code.upper())
    if not cur:
        raise HTTPException(status_code=404, detail="currency_not_found")
    return CurrencyOut.model_validate(cur, from_attributes=True).model_dump()


class ExchangeRateOut(BaseModel):
    base: str
    quote: Optional[str] = None
    date: str
    rate: Optional[Decimal] = None
    effective_date: Optional[str] = None


@router.get("/exchange-rates")
def get_exchange_rates(
    base: str = Query(..., min_length=3, max_length=3),
    quote: Optional[str] = Query(None, min_length=3, max_length=3),
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    base = base.upper()
    qdate = date_cls.fromisoformat(date) if date else datetime.now(timezone.utc).date()

    if quote:
        quote = quote.upper()
        sub = (
            db.query(func.max(ExchangeRate.rate_date))
            .filter(
                ExchangeRate.base_code == base,
                ExchangeRate.quote_code == quote,
                ExchangeRate.rate_date <= qdate,
            )
            .scalar()
        )
        if not sub:
            raise HTTPException(status_code=404, detail="rate_not_found")
        row = (
            db.query(ExchangeRate)
            .filter(
                ExchangeRate.base_code == base,
                ExchangeRate.quote_code == quote,
                ExchangeRate.rate_date == sub,
            )
            .first()
        )
        return {
            "base": base,
            "quote": quote,
            "date": qdate.isoformat(),
            "rate": Decimal(row.rate),
            "effective_date": row.rate_date.isoformat(),
        }
    else:
        # return map of quote->rate for the date (with fallback per pair)
        rates: Dict[str, Dict[str, Any]] = {}
        # find all quotes available for base with rate_date <= qdate and choose latest per quote
        subq = (
            db.query(
                ExchangeRate.quote_code.label("quote"),
                func.max(ExchangeRate.rate_date).label("max_date"),
            )
            .filter(ExchangeRate.base_code == base, ExchangeRate.rate_date <= qdate)
            .group_by(ExchangeRate.quote_code)
            .subquery()
        )
        rows = (
            db.query(ExchangeRate)
            .join(
                subq,
                (ExchangeRate.quote_code == subq.c.quote)
                & (ExchangeRate.rate_date == subq.c.max_date),
            )
            .filter(ExchangeRate.base_code == base)
            .all()
        )
        for r in rows:
            rates[r.quote_code] = {
                "rate": Decimal(r.rate),
                "effective_date": r.rate_date.isoformat(),
            }
        if not rates:
            raise HTTPException(status_code=404, detail="rate_not_found")
        return {"base": base, "date": qdate.isoformat(), "rates": rates}


class ConvertRequest(BaseModel):
    amount: Decimal = Field(...)
    from_currency: str = Field(..., min_length=3, max_length=3, alias="from")
    to_currency: str = Field(..., min_length=3, max_length=3, alias="to")
    date: Optional[str] = None

    @validator("amount")
    def _quantize(cls, v: Decimal):
        return v.quantize(Decimal("0.000001"))


class ConvertResponse(BaseModel):
    amount: Decimal
    from_currency: str
    to_currency: str
    rate: Decimal
    converted: Decimal
    effective_date: str


_idem_cache: Dict[str, Dict[str, Any]] = {}


@router.post("/convert", response_model=ConvertResponse)
def convert_amount(req: Request, body: ConvertRequest, db: Session = Depends(get_db)):
    # Idempotency-Key simple process-local cache
    idem = req.headers.get("Idempotency-Key")
    cache_key = f"{idem}:{body.json()}" if idem else None
    if cache_key and cache_key in _idem_cache:
        return _idem_cache[cache_key]

    base = body.from_currency.upper()
    quote = body.to_currency.upper()
    qdate = (
        date_cls.fromisoformat(body.date) if body.date else datetime.now(timezone.utc).date()
    )
    sub = (
        db.query(func.max(ExchangeRate.rate_date))
        .filter(
            ExchangeRate.base_code == base,
            ExchangeRate.quote_code == quote,
            ExchangeRate.rate_date <= qdate,
        )
        .scalar()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="rate_not_found")
    row = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.base_code == base,
            ExchangeRate.quote_code == quote,
            ExchangeRate.rate_date == sub,
        )
        .first()
    )
    rate = Decimal(row.rate)
    converted = (body.amount * rate).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    resp = ConvertResponse(
        amount=body.amount,
        from_currency=base,
        to_currency=quote,
        rate=rate,
        converted=converted,
        effective_date=row.rate_date.isoformat(),
    )
    if cache_key:
        _idem_cache[cache_key] = resp.dict()
    return resp


class CurrencyUpsert(BaseModel):
    code: str
    name: str
    symbol: Optional[str] = None
    scale: int

    @validator("code")
    def _code(cls, v: str):
        v2 = v.upper()
        if len(v2) != 3 or not v2.isalpha():
            raise ValueError("invalid_code")
        return v2

    @validator("scale")
    def _scale(cls, v: int):
        if v < 0 or v > 6:
            raise ValueError("invalid_scale")
        return v


@router.post("/currencies", response_model=CurrencyOut)
def upsert_currency(payload: CurrencyUpsert, db: Session = Depends(get_db)):
    code = payload.code
    cur = db.get(Currency, code)
    if cur:
        cur.name = payload.name
        cur.symbol = payload.symbol
        cur.scale = payload.scale
    else:
        cur = Currency(code=code, name=payload.name, symbol=payload.symbol, scale=payload.scale)
        db.add(cur)
    db.commit()
    db.refresh(cur)
    return cur


class CurrencyPatch(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    scale: Optional[int] = None


@router.patch("/currencies/{code}", response_model=CurrencyOut)
def patch_currency(code: str, payload: CurrencyPatch, db: Session = Depends(get_db)):
    cur = db.get(Currency, code.upper())
    if not cur:
        raise HTTPException(status_code=404, detail="currency_not_found")
    if payload.name is not None:
        cur.name = payload.name
    if payload.symbol is not None:
        cur.symbol = payload.symbol
    if payload.scale is not None:
        if payload.scale < 0 or payload.scale > 6:
            raise HTTPException(status_code=422, detail="invalid_scale")
        cur.scale = payload.scale
    db.commit()
    db.refresh(cur)
    return cur


@router.put("/currencies/bulk")
def bulk_upsert(items: List[CurrencyUpsert], db: Session = Depends(get_db)):
    results = []
    for it in items:
        cur = db.get(Currency, it.code)
        status = "updated" if cur else "created"
        if cur:
            cur.name = it.name
            cur.symbol = it.symbol
            cur.scale = it.scale
        else:
            cur = Currency(code=it.code, name=it.name, symbol=it.symbol, scale=it.scale)
            db.add(cur)
        results.append({"code": it.code, "status": status})
    db.commit()
    return {"results": results}
