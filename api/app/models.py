from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Numeric,
    String,
    Integer,
    BigInteger,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (
        {"schema": "currency"},
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    scale: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        CheckConstraint("rate > 0", name="ck_exchange_rates__positive"),
        Index("idx_exchange_rates__pair_date_desc", "base_code", "quote_code", "rate_date"),
        {"schema": "currency"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    base_code: Mapped[str] = mapped_column(String, nullable=False)
    quote_code: Mapped[str] = mapped_column(String, nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # index defined in __table_args__


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users__username"),
        UniqueConstraint("email", name="uq_users__email"),
        {"schema": "user"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String, nullable=True)
    email_verification_token: Mapped[str | None] = mapped_column(String, nullable=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    is_bot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class UserPreference(Base):
    __tablename__ = "user_prefs"
    __table_args__ = (
        {"schema": "user"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    base_currency: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="zh-CN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    __table_args__ = (
        CheckConstraint("name <> ''", name="ck_expense_categories__name_not_empty"),
        UniqueConstraint("user_id", "name", name="uq_expense_categories__user_name"),
        {"schema": "expense"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_expenses__amount_positive"),
        {"schema": "expense"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        _id_type,
        ForeignKey("expense.expense_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    merchant: Mapped[str | None] = mapped_column(String, nullable=True)
    paid_account_id: Mapped[int | None] = mapped_column(_id_type, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
