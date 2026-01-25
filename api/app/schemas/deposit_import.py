from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class ImportInstitutionItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., pattern=r"^(bank|broker|other)$")
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|closed)$")

    @validator("name")
    def _strip_name(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_value")
        return v2


class ImportProductItem(BaseModel):
    institution_name: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    product_type: str = Field("deposit", pattern=r"^(deposit|investment|securities|other)$")
    currency: str = Field(..., min_length=3, max_length=3)
    status: str = Field("active", pattern=r"^(active|inactive|closed)$")
    risk_level: str = Field("stable", pattern=r"^(flexible|stable|high_risk)$")

    @validator("institution_name", "name")
    def _strip_keys(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_value")
        return v2



class ImportBalanceItem(BaseModel):
    institution_name: str = Field(..., min_length=1, max_length=128)
    product_name: str = Field(..., min_length=1, max_length=128)
    as_of: datetime
    amount: Decimal = Field(..., ge=0)

    @validator("institution_name", "product_name")
    def _strip_balance_keys(cls, v: str):
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
    institution_name: str
    institution_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class ImportProductResult(BaseModel):
    institution_name: str
    product_name: str
    product_id: Optional[int] = None
    status: str
    error: Optional[str] = None


class ImportBalanceResult(BaseModel):
    institution_name: str
    product_name: str
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
