from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import resolve_user_id
from ..db import SessionLocal
from ..importers.deposit_excel import parse_deposit_import_file
from ..models import Currency, FinancialProduct, Institution, ProductBalance, User
from ..schemas.deposit_import import (
    ImportBalanceResult,
    ImportDepositRequest,
    ImportDepositResponse,
    ImportInstitutionResult,
    ImportProductResult,
    ImportSectionResult,
)

router = APIRouter(prefix="/v1", tags=["deposit"])

_idem_cache: dict[str, dict] = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_current_user(
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


def _ensure_currency(code: str, db: Session) -> str:
    if not code or len(code) != 3 or not code.isalpha():
        raise HTTPException(status_code=422, detail="invalid_currency")
    code = code.upper()
    if not db.get(Currency, code):
        raise HTTPException(status_code=422, detail="unknown_currency")
    return code


def _require_delete_confirm(req: Request, hard: bool) -> None:
    key = req.headers.get("X-Confirm-Delete")
    if hard:
        if key != "HARD-YES":
            raise HTTPException(status_code=412, detail="confirm_delete_required")
    else:
        if key != "YES":
            raise HTTPException(status_code=412, detail="confirm_delete_required")


class InstitutionIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., pattern=r"^(bank|broker|other)$")

    @validator("name")
    def _strip_name(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_name")
        return v2


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    status: str
    product_number: int = 0


class InstitutionPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    type: Optional[str] = Field(default=None, pattern=r"^(bank|broker|other)$")

    @validator("name")
    def _strip_name(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_name")
        return v2


class InstitutionsOut(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
    data: List[InstitutionOut]


class ProductIn(BaseModel):
    institution_id: int
    name: str = Field(..., min_length=1, max_length=128)
    product_type: str = Field("deposit", pattern=r"^(deposit|investment|securities|other)$")
    currency: str = Field(..., min_length=3, max_length=3)
    status: str = Field("active", pattern=r"^(active|inactive|closed)$")
    risk_level: str = Field("stable", pattern=r"^(flexible|stable|high_risk)$")
    amount: Optional[Decimal] = Field(default=None, ge=0)

    @validator("name")
    def _strip_name(cls, v: str):
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_name")
        return v2

    @validator("amount")
    def _quantize_amount(cls, v: Optional[Decimal]):
        if v is None:
            return v
        return v.quantize(Decimal("0.000001"))


class ProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    product_type: Optional[str] = Field(default=None, pattern=r"^(deposit|investment|securities|other)$")
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive|closed)$")
    risk_level: Optional[str] = Field(default=None, pattern=r"^(flexible|stable|high_risk)$")

    @validator("name")
    def _strip_name(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        if not v2:
            raise ValueError("empty_name")
        return v2

class ProductStatusPatch(BaseModel):
    status: str = Field(..., pattern=r"^(active|inactive|closed)$")

class ProductBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_id: int
    name: str
    product_type: str
    currency: str
    status: str
    risk_level: str
    amount: Decimal
    amount_updated_at: datetime


class ProductOut(ProductBaseOut):
    institution_name: str
    institution_type: str


class ProductsOut(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
    data: List[ProductOut]


def _product_response(prod: FinancialProduct, inst: Institution) -> dict:
    prod_data = ProductBaseOut.model_validate(prod, from_attributes=True).model_dump()
    prod_data["institution_name"] = inst.name
    prod_data["institution_type"] = inst.type
    return prod_data


class BalanceIn(BaseModel):
    amount: Decimal = Field(..., ge=0)
    as_of: datetime

    @validator("amount")
    def _quantize_amount(cls, v: Decimal):
        return v.quantize(Decimal("0.000001"))


class BalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    amount: Decimal
    as_of: datetime


class BalancesOut(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
    data: List[BalanceOut]


class LatestBalanceItem(BaseModel):
    product_id: int
    amount: Decimal = Field(..., ge=0)
    as_of: Optional[datetime] = None

    @validator("amount")
    def _quantize_latest_amount(cls, v: Decimal):
        return v.quantize(Decimal("0.000001"))


class LatestBalanceBatchRequest(BaseModel):
    items: List[LatestBalanceItem] = Field(default_factory=list)


class LatestBalanceResult(BaseModel):
    product_id: int
    as_of: datetime
    status: str
    error: Optional[str] = None


class LatestBalanceBatchResponse(BaseModel):
    total: int
    created: int
    updated: int
    failed: int
    items: List[LatestBalanceResult]




@router.post("/institutions", status_code=201, response_model=InstitutionOut)
def create_institution(
    req: Request,
    payload: InstitutionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"inst:{current_user.id}:{idem}:{payload.model_dump_json()}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    existing = (
        db.query(Institution)
        .filter(Institution.user_id == current_user.id, Institution.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="institution_exists")

    now = _now()
    inst = Institution(
        user_id=current_user.id,
        name=payload.name,
        type=payload.type,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    resp = InstitutionOut.model_validate(inst, from_attributes=True).model_dump()
    resp["product_number"] = 0
    if cache_key:
        _idem_cache[cache_key] = resp
    return resp


@router.get("/institutions", response_model=InstitutionsOut)
def list_institutions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    type: Optional[str] = Query(None, pattern=r"^(bank|broker|other)$"),
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Institution, func.count(FinancialProduct.id).label("product_number"))
        .outerjoin(FinancialProduct, FinancialProduct.institution_id == Institution.id)
        .filter(Institution.user_id == current_user.id)
        .filter(Institution.status != "closed")
    )
    if type:
        query = query.filter(Institution.type == type)
    if name:
        name_filter = f"%{name.strip()}%"
        query = query.filter(Institution.name.ilike(name_filter))
    query = query.group_by(Institution.id)
    total = query.with_entities(Institution.id).distinct().count()
    rows = (
        query.order_by(Institution.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = []
    for inst, product_number in rows:
        inst_data = InstitutionOut.model_validate(inst, from_attributes=True).model_dump()
        inst_data["product_number"] = product_number
        data.append(inst_data)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "data": data,
    }


@router.patch("/institutions/{institution_id}", response_model=InstitutionOut)
def patch_institution(
    institution_id: int,
    payload: InstitutionPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inst = (
        db.query(Institution)
        .filter(Institution.id == institution_id, Institution.user_id == current_user.id)
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="institution_not_found")

    if payload.name is not None and payload.name != inst.name:
        dup = (
            db.query(Institution)
            .filter(Institution.user_id == current_user.id, Institution.name == payload.name)
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="institution_exists")
        inst.name = payload.name
    if payload.type is not None:
        inst.type = payload.type
    inst.updated_at = _now()
    db.commit()
    db.refresh(inst)
    return InstitutionOut.model_validate(inst, from_attributes=True).model_dump()


@router.delete("/institutions/{institution_id}", response_model=InstitutionOut)
def delete_institution(
    institution_id: int,
    req: Request,
    hard: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_delete_confirm(req, hard)
    inst = (
        db.query(Institution)
        .filter(Institution.id == institution_id, Institution.user_id == current_user.id)
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="institution_not_found")

    if hard:
        db.delete(inst)
        db.commit()
        return InstitutionOut.model_validate(inst, from_attributes=True).model_dump()

    if inst.status == "closed":
        raise HTTPException(status_code=409, detail="institution_already_closed")

    now = _now()
    inst.status = "closed"
    inst.updated_at = now
    db.query(FinancialProduct).filter(FinancialProduct.institution_id == inst.id).update(
        {"status": "closed", "updated_at": now}
    )
    db.commit()
    db.refresh(inst)
    return InstitutionOut.model_validate(inst, from_attributes=True).model_dump()


@router.post("/products", status_code=201, response_model=ProductOut)
def create_product(
    req: Request,
    payload: ProductIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"prod:{current_user.id}:{idem}:{payload.model_dump_json()}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    inst = (
        db.query(Institution)
        .filter(Institution.id == payload.institution_id, Institution.user_id == current_user.id)
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="institution_not_found")

    currency = _ensure_currency(payload.currency, db)
    now = _now()
    prod = FinancialProduct(
        institution_id=inst.id,
        name=payload.name,
        product_type=payload.product_type,
        currency=currency,
        status=payload.status,
        risk_level=payload.risk_level,
        amount=payload.amount or Decimal("0"),
        amount_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    resp = _product_response(prod, inst)
    if cache_key:
        _idem_cache[cache_key] = resp
    return resp


@router.get("/products", response_model=ProductsOut)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    institution_id: Optional[int] = None,
    product_type: Optional[str] = Query(None, pattern=r"^(deposit|investment|securities|other)$"),
    status: Optional[str] = Query(None, pattern=r"^(active|inactive|closed)$"),
    risk_level: Optional[str] = Query(None, pattern=r"^(flexible|stable|high_risk)$"),
    currency: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(FinancialProduct, Institution)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(Institution.user_id == current_user.id)
        .filter(FinancialProduct.status != "closed")
    )
    if institution_id:
        query = query.filter(FinancialProduct.institution_id == institution_id)
    if product_type:
        query = query.filter(FinancialProduct.product_type == product_type)
    if status:
        query = query.filter(FinancialProduct.status == status)
    if risk_level:
        query = query.filter(FinancialProduct.risk_level == risk_level)
    if currency:
        curr_code = _ensure_currency(currency, db)
        query = query.filter(FinancialProduct.currency == curr_code)

    total = query.count()
    rows = (
        query.order_by(FinancialProduct.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = [_product_response(prod, inst) for prod, inst in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "data": data,
    }


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: int,
    payload: ProductPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(FinancialProduct, Institution)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(FinancialProduct.id == product_id, Institution.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="product_not_found")
    prod, inst = row

    if payload.name is not None:
        prod.name = payload.name
    if payload.product_type is not None:
        prod.product_type = payload.product_type
    if payload.status is not None:
        prod.status = payload.status
    if payload.risk_level is not None:
        prod.risk_level = payload.risk_level
    prod.updated_at = _now()
    db.commit()
    db.refresh(prod)
    return _product_response(prod, inst)

@router.patch("/products/{product_id}/status", response_model=ProductStatusPatch)
def patch_product_status(
    product_id: int,
    payload: ProductStatusPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = (
        db.query(FinancialProduct, Institution)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(FinancialProduct.id == product_id, Institution.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="product_not_found")
    prod, inst = row

    prod.status = payload.status
    prod.updated_at = _now()
    db.commit()
    db.refresh(prod)
    return _product_response(prod, inst)

@router.delete("/products/{product_id}", response_model=ProductOut)
def delete_product(
    product_id: int,
    req: Request,
    hard: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_delete_confirm(req, hard)
    row = (
        db.query(FinancialProduct, Institution)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(FinancialProduct.id == product_id, Institution.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="product_not_found")
    prod, inst = row

    if hard:
        db.delete(prod)
        db.commit()
        return _product_response(prod, inst)

    if prod.status == "closed":
        raise HTTPException(status_code=409, detail="product_already_closed")

    prod.status = "closed"
    prod.updated_at = _now()
    db.commit()
    db.refresh(prod)
    return _product_response(prod, inst)


@router.get("/products/{product_id}/balances", response_model=BalancesOut)
def list_balances(
    product_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prod = (
        db.query(FinancialProduct)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(FinancialProduct.id == product_id, Institution.user_id == current_user.id)
        .first()
    )
    if not prod:
        raise HTTPException(status_code=404, detail="product_not_found")

    query = db.query(ProductBalance).filter(ProductBalance.product_id == product_id)
    if from_dt:
        query = query.filter(ProductBalance.as_of >= from_dt)
    if to_dt:
        query = query.filter(ProductBalance.as_of <= to_dt)

    total = query.count()
    rows = (
        query.order_by(ProductBalance.as_of.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = [BalanceOut.model_validate(row, from_attributes=True).model_dump() for row in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "data": data,
    }


@router.post(
    "/institutions/{institution_id}/products/balances/latest",
    status_code=201,
    response_model=LatestBalanceBatchResponse,
)
def upsert_latest_balances(
    institution_id: int,
    payload: LatestBalanceBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inst = (
        db.query(Institution)
        .filter(Institution.id == institution_id, Institution.user_id == current_user.id)
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="institution_not_found")

    seen: set[int] = set()
    dupes: set[int] = set()
    for item in payload.items:
        if item.product_id in seen:
            dupes.add(item.product_id)
        else:
            seen.add(item.product_id)
    if dupes:
        dup_list = ",".join(str(pid) for pid in sorted(dupes))
        raise HTTPException(status_code=422, detail=f"duplicate_product_id:{dup_list}")

    product_ids = [item.product_id for item in payload.items]
    products = (
        db.query(FinancialProduct)
        .filter(
            FinancialProduct.institution_id == institution_id,
            FinancialProduct.id.in_(product_ids),
        )
        .all()
    )
    prod_map = {p.id: p for p in products}

    results: List[LatestBalanceResult] = []
    for item in payload.items:
        prod = prod_map.get(item.product_id)
        if not prod:
            results.append(
                LatestBalanceResult(
                    product_id=item.product_id,
                    as_of=item.as_of or _now(),
                    status="failed",
                    error="product_not_found",
                )
            )
            continue

        as_of = item.as_of or _now()
        existing = (
            db.query(ProductBalance)
            .filter(ProductBalance.product_id == prod.id, ProductBalance.as_of == as_of)
            .first()
        )
        now = _now()
        if existing:
            existing.amount = item.amount
            existing.updated_at = now
            try:
                db.commit()
            except Exception:
                db.rollback()
                results.append(
                    LatestBalanceResult(
                        product_id=prod.id,
                        as_of=as_of,
                        status="failed",
                        error="balance_update_failed",
                    )
                )
                continue
            results.append(
                LatestBalanceResult(
                    product_id=prod.id,
                    as_of=as_of,
                    status="updated",
                )
            )
            continue

        bal = ProductBalance(
            product_id=prod.id,
            amount=item.amount,
            as_of=as_of,
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(bal)
            db.commit()
        except Exception:
            db.rollback()
            results.append(
                LatestBalanceResult(
                    product_id=prod.id,
                    as_of=as_of,
                    status="failed",
                    error="balance_create_failed",
                )
            )
            continue

        results.append(
            LatestBalanceResult(
                product_id=prod.id,
                as_of=as_of,
                status="created",
            )
        )

    total = len(results)
    created = sum(1 for r in results if r.status == "created")
    updated = sum(1 for r in results if r.status == "updated")
    failed = sum(1 for r in results if r.status == "failed")
    return LatestBalanceBatchResponse(
        total=total,
        created=created,
        updated=updated,
        failed=failed,
        items=results,
    )


@router.post("/products/{product_id}/balances", status_code=201, response_model=BalanceOut)
def create_balance(
    product_id: int,
    payload: BalanceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prod = (
        db.query(FinancialProduct)
        .join(Institution, FinancialProduct.institution_id == Institution.id)
        .filter(FinancialProduct.id == product_id, Institution.user_id == current_user.id)
        .first()
    )
    if not prod:
        raise HTTPException(status_code=404, detail="product_not_found")

    existing = (
        db.query(ProductBalance)
        .filter(ProductBalance.product_id == product_id, ProductBalance.as_of == payload.as_of)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="balance_exists")

    now = _now()
    bal = ProductBalance(
        product_id=product_id,
        amount=payload.amount,
        as_of=payload.as_of,
        created_at=now,
        updated_at=now,
    )
    db.add(bal)
    db.commit()
    db.refresh(bal)
    return BalanceOut.model_validate(bal, from_attributes=True).model_dump()


def _ensure_unique_keys(items: List[BaseModel], key_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        key = getattr(item, key_name)
        if key in seen:
            duplicates.add(key)
        else:
            seen.add(key)
    if duplicates:
        dup_list = ",".join(sorted(duplicates))
        raise HTTPException(status_code=422, detail=f"duplicate_{key_name}:{dup_list}")


def _import_deposit_payload(
    payload: ImportDepositRequest,
    db: Session,
    current_user: User,
) -> ImportDepositResponse:
    _ensure_unique_keys(payload.institutions, "institution_key")
    _ensure_unique_keys(payload.products, "product_key")

    inst_keys = {item.institution_key for item in payload.institutions}
    missing_inst = {
        item.institution_key for item in payload.products if item.institution_key not in inst_keys
    }
    if missing_inst:
        missing_list = ",".join(sorted(missing_inst))
        raise HTTPException(status_code=422, detail=f"missing_institution_key:{missing_list}")

    prod_keys = {item.product_key for item in payload.products}
    missing_prod = {item.product_key for item in payload.product_balances if item.product_key not in prod_keys}
    if missing_prod:
        missing_list = ",".join(sorted(missing_prod))
        raise HTTPException(status_code=422, detail=f"missing_product_key:{missing_list}")

    inst_results: List[ImportInstitutionResult] = []
    prod_results: List[ImportProductResult] = []
    bal_results: List[ImportBalanceResult] = []
    inst_map: dict[str, int] = {}
    prod_map: dict[str, int] = {}

    for item in payload.institutions:
        existing = (
            db.query(Institution)
            .filter(Institution.user_id == current_user.id, Institution.name == item.name)
            .first()
        )
        if existing:
            inst_map[item.institution_key] = existing.id
            inst_results.append(
                ImportInstitutionResult(
                    institution_key=item.institution_key,
                    institution_id=existing.id,
                    status="exists",
                )
            )
            continue

        now = _now()
        inst = Institution(
            user_id=current_user.id,
            name=item.name,
            type=item.type,
            status=item.status or "active",
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(inst)
            db.commit()
            db.refresh(inst)
        except Exception:
            db.rollback()
            inst_results.append(
                ImportInstitutionResult(
                    institution_key=item.institution_key,
                    status="failed",
                    error="institution_create_failed",
                )
            )
            continue

        inst_map[item.institution_key] = inst.id
        inst_results.append(
            ImportInstitutionResult(
                institution_key=item.institution_key,
                institution_id=inst.id,
                status="created",
            )
        )

    for item in payload.products:
        inst_id = inst_map.get(item.institution_key)
        if not inst_id:
            prod_results.append(
                ImportProductResult(
                    product_key=item.product_key,
                    institution_key=item.institution_key,
                    status="failed",
                    error="institution_key_not_found",
                )
            )
            continue

        try:
            currency = _ensure_currency(item.currency, db)
        except HTTPException:
            prod_results.append(
                ImportProductResult(
                    product_key=item.product_key,
                    institution_key=item.institution_key,
                    status="failed",
                    error="invalid_currency",
                )
            )
            continue

        now = _now()
        prod = FinancialProduct(
            institution_id=inst_id,
            name=item.name,
            product_type=item.product_type,
            currency=currency,
            status=item.status,
            risk_level=item.risk_level,
            amount=item.amount or Decimal("0"),
            amount_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(prod)
            db.commit()
            db.refresh(prod)
        except Exception:
            db.rollback()
            prod_results.append(
                ImportProductResult(
                    product_key=item.product_key,
                    institution_key=item.institution_key,
                    status="failed",
                    error="product_create_failed",
                )
            )
            continue

        prod_map[item.product_key] = prod.id
        prod_results.append(
            ImportProductResult(
                product_key=item.product_key,
                institution_key=item.institution_key,
                product_id=prod.id,
                status="created",
            )
        )

    for item in payload.product_balances:
        prod_id = prod_map.get(item.product_key)
        if not prod_id:
            bal_results.append(
                ImportBalanceResult(
                    product_key=item.product_key,
                    as_of=item.as_of,
                    status="failed",
                    error="product_key_not_found",
                )
            )
            continue

        existing = (
            db.query(ProductBalance)
            .filter(ProductBalance.product_id == prod_id, ProductBalance.as_of == item.as_of)
            .first()
        )
        if existing:
            bal_results.append(
                ImportBalanceResult(
                    product_key=item.product_key,
                    as_of=item.as_of,
                    status="exists",
                )
            )
            continue

        now = _now()
        bal = ProductBalance(
            product_id=prod_id,
            amount=item.amount,
            as_of=item.as_of,
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(bal)
            db.commit()
            db.refresh(bal)
        except Exception:
            db.rollback()
            bal_results.append(
                ImportBalanceResult(
                    product_key=item.product_key,
                    as_of=item.as_of,
                    status="failed",
                    error="balance_create_failed",
                )
            )
            continue

        bal_results.append(
            ImportBalanceResult(
                product_key=item.product_key,
                as_of=item.as_of,
                status="created",
            )
        )

    def _section_stats(results: List[BaseModel]) -> ImportSectionResult:
        total = len(results)
        created = sum(1 for r in results if r.status == "created")
        exists = sum(1 for r in results if r.status == "exists")
        failed = sum(1 for r in results if r.status == "failed")
        return ImportSectionResult(total=total, created=created, exists=exists, failed=failed)

    return ImportDepositResponse(
        institutions=_section_stats(inst_results),
        products=_section_stats(prod_results),
        product_balances=_section_stats(bal_results),
        institution_items=inst_results,
        product_items=prod_results,
        balance_items=bal_results,
    )


@router.post("/import/deposit", status_code=201, response_model=ImportDepositResponse)
def import_deposit(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = parse_deposit_import_file(file)
    return _import_deposit_payload(payload, db, current_user)
