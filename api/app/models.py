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
    JSON,
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
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_login_token: Mapped[str | None] = mapped_column(String, nullable=True)
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


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint(
            "token_type IN ('email_verification','password_reset')",
            name="ck_auth_tokens__type",
        ),
        UniqueConstraint("token", name="uq_auth_tokens__token"),
        Index("idx_auth_tokens__user_type", "user_id", "token_type"),
        {"schema": "user"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String, nullable=False)
    token_type: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
    tax: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
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
    name: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    file_id: Mapped[int | None] = mapped_column(
        _id_type,
        ForeignKey("file.files.id", ondelete="SET NULL"),
        nullable=True,
    )
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


class SchedulerJob(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('active','paused','archived')", name="ck_jobs__status"),
        CheckConstraint("advance_minutes BETWEEN 0 AND 10080", name="ck_jobs__advance"),
        Index("idx_jobs__user_id", "user_id"),
        {"schema": "scheduler"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    rule: Mapped[str] = mapped_column(String, nullable=False)
    first_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    advance_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel: Mapped[str] = mapped_column(String, nullable=False, default="telegram")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchedulerJobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint("job_id", "period_key", name="uq_job_runs__job_period"),
        CheckConstraint(
            "status IN ('pending','sent','confirmed','skipped','snoozed','cancelled')",
            name="ck_job_runs__status",
        ),
        Index("idx_job_runs__job_scheduled", "job_id", "scheduled_at"),
        {"schema": "scheduler"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("scheduler.jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_key: Mapped[str] = mapped_column(String, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchedulerReminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        {"schema": "scheduler"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("scheduler.job_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SchedulerConfirmation(Base):
    __tablename__ = "confirmations"
    __table_args__ = (
        UniqueConstraint("job_run_id", "idempotency_key", name="uq_confirmations__run_idem"),
        CheckConstraint(
            "action IN ('complete','skip','snooze','cancel')",
            name="ck_confirmations__action",
        ),
        Index("idx_confirmations__run_confirmed", "job_run_id", "confirmed_at"),
        {"schema": "scheduler"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("scheduler.job_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_institutions__user_name"),
        {"schema": "deposit"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type, ForeignKey("user.users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinancialProduct(Base):
    __tablename__ = "financial_products"
    __table_args__ = (
        CheckConstraint(
            "product_type IN ('deposit','investment','securities','other')",
            name="ck_fin_products__type",
        ),
        CheckConstraint(
            "status IN ('active','inactive','closed')",
            name="ck_fin_products__status",
        ),
        CheckConstraint(
            "risk_level IN ('flexible','stable','high_risk')",
            name="ck_fin_products__risk",
        ),
        Index("idx_fin_products__institution_id", "institution_id"),
        {"schema": "deposit"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    institution_id: Mapped[int] = mapped_column(
        _id_type, ForeignKey("deposit.institutions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    product_type: Mapped[str] = mapped_column(String, nullable=False, default="deposit")
    currency: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="stable")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    amount_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductBalance(Base):
    __tablename__ = "product_balances"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_product_balances__amount_nonneg"),
        UniqueConstraint("product_id", "as_of", name="uq_product_balances__product_asof"),
        Index("idx_product_balances__product_as_of_desc", "product_id", "as_of"),
        {"schema": "deposit"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        _id_type, ForeignKey("deposit.financial_products.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FileAsset(Base):
    __tablename__ = "files"
    __table_args__ = (
        {"schema": "file"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _id_type,
        ForeignKey("user.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
