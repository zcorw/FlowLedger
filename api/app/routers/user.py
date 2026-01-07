from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Currency, User, UserPreference
from ..auth import (
    AUTH_TOKEN_TTL_SECONDS,
    PASSWORD_MIN_LENGTH,
    hash_password,
    resolve_user_id,
    verify_password,
)
from ..auth import generate_access_token
from ..email_service import send_verification_email

router = APIRouter(prefix="/v1", tags=["user"])


DEFAULT_BASE_CURRENCY = os.getenv("DEFAULT_CURRENCY", "USD").upper()
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANG", "zh-CN")
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS = int(os.getenv("EMAIL_VERIFICATION_TOKEN_TTL_SECONDS", "86400"))
EMAIL_VERIFICATION_ENABLED = os.getenv("EMAIL_VERIFICATION_ENABLED", "true").lower() == "true"
REGISTRATION_DAILY_LIMIT_NO_EMAIL = int(os.getenv("REGISTRATION_DAILY_LIMIT_NO_EMAIL", "50"))
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

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
    username: Optional[str] = None
    email: Optional[str] = None
    email_verified: bool = False
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


class AuthRegisterPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)
    email: EmailStr
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    language: Optional[str] = Field(default=None, min_length=2, max_length=32)


class AuthLoginPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = AUTH_TOKEN_TTL_SECONDS
    user: UserOut
    preferences: PreferenceOut


def get_current_user(
    db: Session = Depends(get_db),
    user_id: int = Depends(resolve_user_id),
) -> User:
    user = db.get(User, user_id)
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


def _normalize_username(username: str) -> str:
    uname = username.strip()
    if not USERNAME_PATTERN.match(uname):
        raise HTTPException(status_code=422, detail="invalid_username")
    return uname.lower()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _apply_credentials(
    user: User,
    username: Optional[str],
    password: Optional[str],
    email: Optional[str],
    db: Session,
):
    if email:
        norm_email = _normalize_email(email)
        existing_email = db.query(User).filter(User.email == norm_email).first()
        if existing_email:
            raise HTTPException(status_code=409, detail="email_taken")
        user.email = norm_email
    if username is None:
        return
    if not password:
        raise HTTPException(status_code=422, detail="password_required")
    uname = _normalize_username(username)
    existing = db.query(User).filter(User.username == uname).first()
    if existing:
        raise HTTPException(status_code=409, detail="username_taken")
    salt, password_hash = hash_password(password)
    user.username = uname
    user.password_salt = salt
    user.password_hash = password_hash


def _set_email_verification(user: User) -> Optional[str]:
    if not EMAIL_VERIFICATION_ENABLED:
        # user.email_verified_at = _now()
        # user.email_verification_token = None
        # user.email_verification_expires_at = None
        return None
    if not user.email:
        return None
    token = secrets.token_urlsafe(32)
    user.email_verification_token = token
    user.email_verification_expires_at = _now() + timedelta(
        seconds=EMAIL_VERIFICATION_TOKEN_TTL_SECONDS
    )
    user.email_verified_at = None
    return token


def _create_user_with_pref(
    db: Session,
    username: Optional[str],
    password: Optional[str],
    email: Optional[str],
    base_currency: Optional[str],
    timezone: Optional[str],
    language: Optional[str],
) -> tuple[User, UserPreference, Optional[str]]:
    now = _now()
    user = User(is_bot_enabled=True, created_at=now, updated_at=now)
    _apply_credentials(user, username, password, email, db)
    verification_token = _set_email_verification(user)
    db.add(user)
    db.flush()
    pref = UserPreference(
        user_id=user.id,
        base_currency=_validate_currency(base_currency or DEFAULT_BASE_CURRENCY, db),
        timezone=_validate_timezone(timezone or DEFAULT_TIMEZONE),
        language=_validate_language(language or DEFAULT_LANGUAGE),
        created_at=now,
        updated_at=now,
    )
    db.add(pref)
    db.commit()
    db.refresh(user)
    db.refresh(pref)
    return user, pref, verification_token


def _ensure_registration_capacity(db: Session):
    if EMAIL_VERIFICATION_ENABLED:
        return
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.query(User).filter(User.created_at >= start).count()
    if count >= REGISTRATION_DAILY_LIMIT_NO_EMAIL:
        raise HTTPException(status_code=429, detail="registration_limit_reached")


def _issue_auth_response(user: User, pref: UserPreference) -> dict:
    token = generate_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user=user,
        preferences=pref,
    ).model_dump()


@router.post("/users", status_code=201, response_model=UserWithPreference)
def register_user(
    req: Request,
    payload: Optional[AuthRegisterPayload] = Body(default=None),
    db: Session = Depends(get_db),
):
    _ensure_registration_capacity(db)
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"register:{idem}:{payload.model_dump_json() if payload else ''}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    username = payload.username if payload else None
    password = payload.password if payload else None
    user, pref, _ = _create_user_with_pref(
        db=db,
        username=username,
        password=password,
        email=payload.email if payload else None,
        base_currency=payload.base_currency if payload else None,
        timezone=payload.timezone if payload else None,
        language=payload.language if payload else None,
    )
    resp = UserWithPreference(user=user, preferences=pref).model_dump()
    return _cache_or_return(cache_key, resp)


@router.get("/users/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user, from_attributes=True).model_dump()


@router.post("/auth/register", status_code=201, response_model=AuthResponse)
def auth_register(
    req: Request,
    payload: AuthRegisterPayload,
    db: Session = Depends(get_db),
):
    _ensure_registration_capacity(db)
    cache_key = None
    idem = req.headers.get("Idempotency-Key")
    if idem:
        cache_key = f"auth_register:{idem}:{payload.model_dump_json()}"
        if cache_key in _idem_cache:
            return _idem_cache[cache_key]

    username = _normalize_username(payload.username)
    user, pref, verification_token = _create_user_with_pref(
        db=db,
        username=username,
        password=payload.password,
        email=payload.email,
        base_currency=payload.base_currency,
        timezone=payload.timezone,
        language=payload.language,
    )
    if verification_token:
        send_verification_email(user.email, verification_token)
    resp = _issue_auth_response(user, pref)
    return _cache_or_return(cache_key, resp)


@router.post("/auth/login", response_model=AuthResponse)
def auth_login(
    payload: AuthLoginPayload,
    db: Session = Depends(get_db),
):
    username = _normalize_username(payload.username)
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.password_salt or not user.password_hash:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    if not verify_password(payload.password, user.password_salt, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials")
    user.last_login_at = _now()
    db.commit()
    db.refresh(user)
    pref = _ensure_preference(user, db)
    return _issue_auth_response(user, pref)


@router.get("/auth/verify-email", response_model=AuthResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="invalid_or_expired_verification_token")
    if user.email_verification_expires_at and user.email_verification_expires_at < _now():
        raise HTTPException(status_code=400, detail="invalid_or_expired_verification_token")
    user.email_verified_at = _now()
    user.email_verification_token = None
    user.email_verification_expires_at = None
    user.updated_at = _now()
    db.commit()
    db.refresh(user)
    pref = _ensure_preference(user, db)
    return _issue_auth_response(user, pref)


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
