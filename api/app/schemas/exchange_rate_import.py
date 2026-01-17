from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class ImportExchangeRateItem(BaseModel):
    base: str = Field(..., min_length=3, max_length=3)
    quote: str = Field(..., min_length=3, max_length=3)
    rate_date: date
    rate: Decimal = Field(..., gt=0)
    source: Optional[str] = Field(default=None, max_length=64)

    @validator("base", "quote")
    def _code(cls, v: str):
        v2 = v.strip().upper()
        if len(v2) != 3 or not v2.isalpha():
            raise ValueError("invalid_currency")
        return v2

    @validator("rate")
    def _quantize_rate(cls, v: Decimal):
        return v.quantize(Decimal("0.0000000001"))

    @validator("source")
    def _strip_source(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class ImportExchangeRateRequest(BaseModel):
    items: List[ImportExchangeRateItem] = Field(default_factory=list)


class ImportExchangeRateResult(BaseModel):
    base: str
    quote: str
    rate_date: date
    status: str
    error: Optional[str] = None


class ImportExchangeRateResponse(BaseModel):
    total: int
    created: int
    updated: int
    failed: int
    items: List[ImportExchangeRateResult]
