from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, validator
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Currency, Expense, ExpenseCategory, User
from ..auth import resolve_user_id

router = APIRouter(prefix="/v1", tags=["expense"])

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


class CategoryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)

    @validator("name")
    def _strip(cls, v: str):
        name = v.strip()
        if not name:
            raise ValueError("empty_name")
        return name


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


# Idempotent category create scoped per user; duplicate name returns 409
@router.post("/categories", status_code=201, response_model=CategoryOut)
def create_category(
    req: Request,
    payload: CategoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"cat:{current_user.id}:{idem}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    existing = (
        db.query(ExpenseCategory)
        .filter(ExpenseCategory.user_id == current_user.id, ExpenseCategory.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="category_exists")

    now = _now()
    cat = ExpenseCategory(
        user_id=current_user.id,
        name=payload.name,
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    resp = CategoryOut.model_validate(cat, from_attributes=True).model_dump()
    if cache_key:
        _idem_cache[cache_key] = resp
    return resp


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cats = (
        db.query(ExpenseCategory)
        .filter(ExpenseCategory.user_id == current_user.id)
        .order_by(ExpenseCategory.id.asc())
        .all()
    )
    return {"data": [CategoryOut.model_validate(c, from_attributes=True).model_dump() for c in cats]}


class ExpenseIn(BaseModel):
    amount: Decimal = Field(...)
    currency: str = Field(..., min_length=3, max_length=3)
    category_id: Optional[int] = None
    merchant: Optional[str] = Field(default=None, max_length=255)
    paid_account_id: Optional[int] = None
    occurred_at: datetime
    source_ref: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=1024)

    @validator("amount")
    def _amount(cls, v: Decimal):
        v2 = v.quantize(Decimal("0.000001"))
        if v2 < 0:
            raise ValueError("amount_must_be_positive")
        return v2

    @validator("currency")
    def _currency(cls, v: str):
        if not v or len(v) != 3 or not v.isalpha():
            raise ValueError("invalid_currency")
        return v.upper()

    @validator("merchant", "source_ref", "note")
    def _strip_optional(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    currency: str
    category_id: Optional[int] = None
    merchant: Optional[str] = None
    paid_account_id: Optional[int] = None
    occurred_at: datetime
    source_ref: Optional[str] = None
    note: Optional[str] = None


class ExpensePatch(BaseModel):
    amount: Optional[Decimal] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    category_id: Optional[int] = None
    merchant: Optional[str] = Field(default=None, max_length=255)
    paid_account_id: Optional[int] = None
    occurred_at: Optional[datetime] = None
    source_ref: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=1024)

    @validator("amount")
    def _patch_amount(cls, v: Optional[Decimal]):
        if v is None:
            return v
        v2 = v.quantize(Decimal("0.000001"))
        if v2 < 0:
            raise ValueError("amount_must_be_positive")
        return v2

    @validator("currency")
    def _patch_currency(cls, v: Optional[str]):
        if v is None:
            return v
        if not v or len(v) != 3 or not v.isalpha():
            raise ValueError("invalid_currency")
        return v.upper()

    @validator("merchant", "source_ref", "note")
    def _strip_patch_optional(cls, v: Optional[str]):
        if v is None:
            return v
        v2 = v.strip()
        return v2 or None


# Idempotent expense create with currency/category validation; source_ref conflict returns 409
@router.post("/expenses", status_code=201, response_model=ExpenseOut)
def create_expense(
    req: Request,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"exp:{current_user.id}:{idem}:{payload.model_dump_json()}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    _ensure_currency(payload.currency, db)

    if payload.category_id:
        cat = db.get(ExpenseCategory, payload.category_id)
        if not cat or cat.user_id != current_user.id:
            raise HTTPException(status_code=422, detail="invalid_category")

    if payload.source_ref:
        dup = (
            db.query(Expense)
            .filter(Expense.user_id == current_user.id, Expense.source_ref == payload.source_ref)
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="duplicate_source_ref")

    now = _now()
    exp = Expense(
        user_id=current_user.id,
        amount=payload.amount,
        currency=payload.currency,
        category_id=payload.category_id,
        merchant=payload.merchant,
        paid_account_id=payload.paid_account_id,
        occurred_at=payload.occurred_at,
        source_ref=payload.source_ref,
        note=payload.note,
        created_at=now,
        updated_at=now,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    resp = ExpenseOut.model_validate(exp, from_attributes=True).model_dump()
    if cache_key:
        _idem_cache[cache_key] = resp
    return resp


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="expense_not_found")
    return ExpenseOut.model_validate(exp, from_attributes=True).model_dump()


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
def patch_expense(
    expense_id: int,
    payload: ExpensePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="expense_not_found")

    if payload.currency is not None:
        exp.currency = _ensure_currency(payload.currency, db)
    if payload.category_id is not None:
        if payload.category_id:
            cat = db.get(ExpenseCategory, payload.category_id)
            if not cat or cat.user_id != current_user.id:
                raise HTTPException(status_code=422, detail="invalid_category")
        exp.category_id = payload.category_id
    if payload.amount is not None:
        exp.amount = payload.amount
    if payload.merchant is not None:
        exp.merchant = payload.merchant
    if payload.paid_account_id is not None:
        exp.paid_account_id = payload.paid_account_id
    if payload.occurred_at is not None:
        exp.occurred_at = payload.occurred_at
    if payload.source_ref is not None and payload.source_ref != exp.source_ref:
        if payload.source_ref:
            dup = (
                db.query(Expense)
                .filter(Expense.user_id == current_user.id, Expense.source_ref == payload.source_ref)
                .first()
            )
            if dup:
                raise HTTPException(status_code=409, detail="duplicate_source_ref")
        exp.source_ref = payload.source_ref
    if payload.note is not None:
        exp.note = payload.note

    exp.updated_at = _now()
    db.commit()
    db.refresh(exp)
    return ExpenseOut.model_validate(exp, from_attributes=True).model_dump()


@router.delete("/expenses/{expense_id}", response_model=ExpenseOut)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not exp:
        raise HTTPException(status_code=404, detail="expense_not_found")
    db.delete(exp)
    db.commit()
    return ExpenseOut.model_validate(exp, from_attributes=True).model_dump()


class ExpenseListOut(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool
    data: List[ExpenseOut]


# Paginated expense list with optional time range, ordered by occurred_at desc
@router.get("/expenses", response_model=ExpenseListOut)
def list_expenses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Expense).filter(Expense.user_id == current_user.id)
    if from_dt:
        query = query.filter(Expense.occurred_at >= from_dt)
    if to_dt:
        query = query.filter(Expense.occurred_at <= to_dt)

    total = query.count()
    rows = (
        query.order_by(Expense.occurred_at.desc(), Expense.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    data = [ExpenseOut.model_validate(row, from_attributes=True).model_dump() for row in rows]
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
        "data": data,
    }
