from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class ImportInstitutionItem(BaseModel):
    institution_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., pattern=r"^(bank|broker|other)$")
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|closed)$")

    @validator("institution_key", "name")
    def _strip_key_name(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_value")
        return v2


class ImportProductItem(BaseModel):
    product_key: str = Field(..., min_length=1, max_length=64)
    institution_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    product_type: str = Field("deposit", pattern=r"^(deposit|investment|securities|other)$")
    currency: str = Field(..., min_length=3, max_length=3)
    status: str = Field("active", pattern=r"^(active|inactive|closed)$")
    risk_level: str = Field("stable", pattern=r"^(flexible|stable|high_risk)$")
    amount: Optional[Decimal] = Field(default=None, ge=0)

    @validator("product_key", "institution_key", "name")
    def _strip_keys(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_value")
        return v2

    @validator("amount")
    def _quantize_amount(cls, v: Optional[Decimal]):
        if v is None:
            return v
        return v.quantize(Decimal("0.000001"))


class ImportBalanceItem(BaseModel):
    product_key: str = Field(..., min_length=1, max_length=64)
    as_of: datetime
    amount: Decimal = Field(..., ge=0)

    @validator("product_key")
    def _strip_product_key(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_value")
        return v2

    @validator("amount")
    def _quantize_balance_amount(cls, v: Decimal):
        return v.quantize(Decimal("0.000001"))


class ImportDepositRequest(BaseModel):
    institutions: List[ImportInstitutionItem] = Field(default_factory=list)
    products: List[ImportProductItem] = Field(default_factory=list)
    product_balances: List[ImportBalanceItem] = Field(default_factory=list)


class ImportInstitutionResult(BaseModel):
    institution_key: str
    institution_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class ImportProductResult(BaseModel):
    product_key: str
    institution_key: str
    product_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class ImportBalanceResult(BaseModel):
    product_key: str
    as_of: datetime
    status: str
    error: Optional[str] = None


class ImportSectionResult(BaseModel):
    total: int
    created: int
    exists: int
    failed: int


class ImportDepositResponse(BaseModel):
    institutions: ImportSectionResult
    products: ImportSectionResult
    product_balances: ImportSectionResult
    institution_items: List[ImportInstitutionResult]
    product_items: List[ImportProductResult]
    balance_items: List[ImportBalanceResult]
