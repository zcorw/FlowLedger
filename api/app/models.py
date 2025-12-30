from __future__ import annotations

from datetime import date, datetime
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
        {"schema": "user"},
    )

    _id_type = BigInteger().with_variant(Integer, "sqlite")

    id: Mapped[int] = mapped_column(_id_type, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    is_bot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
