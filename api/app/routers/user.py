from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Currency, User, UserPreference

router = APIRouter(prefix="/v1", tags=["user"])


DEFAULT_BASE_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD").upper()
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANG", "zh-CN")
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")

_idem_cache: dict[str, dict] = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_currency(code: str, db: Session) -> str:
    if not code or len(code) != 3 or not code.isalpha():
        raise HTTPException(status_code=422, detail="invalid_base_currency")
    code = code.upper()
    if not db.get(Currency, code):
        raise HTTPException(status_code=422, detail="unknown_currency")
    return code


def _validate_timezone(tz: str) -> str:
    if not tz or len(tz) > 64:
        raise HTTPException(status_code=422, detail="invalid_timezone")
    if tz.upper() == "UTC":
        return tz
    try:
        ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="invalid_timezone")
    return tz


def _validate_language(lang: str) -> str:
    if not lang or len(lang) > 32 or not LANGUAGE_PATTERN.match(lang):
        raise HTTPException(status_code=422, detail="invalid_language")
    return lang


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_user_id: Optional[int] = None
    is_bot_enabled: bool


class PreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_currency: str
    timezone: str
    language: str


class UserWithPreference(BaseModel):
    user: UserOut
    preferences: PreferenceOut


class PreferencePatch(BaseModel):
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    language: Optional[str] = Field(default=None, min_length=2, max_length=32)


class LinkTelegramPayload(BaseModel):
    telegram_user_id: int = Field(..., ge=1)
    link_token: Optional[str] = None


def get_current_user(
    db: Session = Depends(get_db),
    x_user_id: Optional[int] = Header(default=None),
) -> User:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")
    return user


def _ensure_preference(user: User, db: Session) -> UserPreference:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if pref:
        return pref
    pref = UserPreference(
        user_id=user.id,
        base_currency=_validate_currency(DEFAULT_BASE_CURRENCY, db),
        timezone=_validate_timezone(DEFAULT_TIMEZONE),
        language=_validate_language(DEFAULT_LANGUAGE),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


def _cache_or_return(key: Optional[str], value: dict):
    if key is None:
        return value
    _idem_cache[key] = value
    return value


def _resolve_link_target(payload: LinkTelegramPayload, current_user: User, db: Session) -> User:
    if payload.link_token:
        match = re.search(r"(\d+)", payload.link_token)
        if not match:
            raise HTTPException(status_code=422, detail="invalid_link_token")
        target_id = int(match.group(1))
        target_user = db.get(User, target_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="link_token_user_not_found")
        return target_user
    return current_user


@router.post("/users", status_code=201, response_model=UserWithPreference)
def register_user(req: Request, db: Session = Depends(get_db)):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"register:{idem}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    now = _now()
    user = User(is_bot_enabled=True, created_at=now, updated_at=now)
    db.add(user)
    db.flush()
    pref = UserPreference(
        user_id=user.id,
        base_currency=_validate_currency(DEFAULT_BASE_CURRENCY, db),
        timezone=_validate_timezone(DEFAULT_TIMEZONE),
        language=_validate_language(DEFAULT_LANGUAGE),
        created_at=now,
        updated_at=now,
    )
    db.add(pref)
    db.commit()
    db.refresh(user)
    db.refresh(pref)
    resp = UserWithPreference(user=user, preferences=pref).model_dump()
    return _cache_or_return(cache_key, resp)


@router.get("/users/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user, from_attributes=True).model_dump()


@router.patch("/users/me/preferences", response_model=PreferenceOut)
def update_preferences(
    req: Request,
    payload: PreferencePatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"pref:{current_user.id}:{idem}:{payload.model_dump_json()}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    pref = _ensure_preference(current_user, db)
    if payload.base_currency is not None:
        pref.base_currency = _validate_currency(payload.base_currency, db)
    if payload.timezone is not None:
        pref.timezone = _validate_timezone(payload.timezone)
    if payload.language is not None:
        pref.language = _validate_language(payload.language)
    pref.updated_at = _now()
    db.commit()
    db.refresh(pref)
    resp = PreferenceOut.model_validate(pref, from_attributes=True).model_dump()
    return _cache_or_return(cache_key, resp)


@router.post("/users/link-telegram", response_model=UserOut)
def link_telegram(
    req: Request,
    payload: LinkTelegramPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"link:{current_user.id}:{idem}:{payload.telegram_user_id}:{payload.link_token}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    target_user = _resolve_link_target(payload, current_user, db)
    existing = db.query(User).filter(User.telegram_user_id == payload.telegram_user_id).first()
    if existing and existing.id != target_user.id:
        raise HTTPException(status_code=409, detail="telegram_user_id_already_bound")
    if target_user.telegram_user_id and target_user.telegram_user_id != payload.telegram_user_id:
        raise HTTPException(status_code=409, detail="user_already_bound")

    target_user.telegram_user_id = payload.telegram_user_id
    target_user.updated_at = _now()
    db.commit()
    db.refresh(target_user)
    resp = UserOut.model_validate(target_user, from_attributes=True).model_dump()
    return _cache_or_return(cache_key, resp)
