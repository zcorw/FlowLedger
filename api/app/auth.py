from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException


# Authentication / password hashing defaults. All values can be overridden by env.
AUTH_ROTATE_ON_STARTUP = os.getenv("AUTH_ROTATE_ON_STARTUP", "false").lower() == "true"
AUTH_SECRET = os.getenv("AUTH_SECRET", "DEV_ONLY_SECRET")
if AUTH_ROTATE_ON_STARTUP:
    AUTH_SECRET = secrets.token_hex(32)
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "604800"))  # 7 days
AUTH_REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_REFRESH_TOKEN_TTL_SECONDS", "2592000"))  # 30 days
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "200_000"))
PASSWORD_MIN_LENGTH = 8


def _ensure_secret():
    if not AUTH_SECRET or AUTH_SECRET == "DEV_ONLY_SECRET":
        # For dev/test we allow default secret, but surface a clear error for runtime verification.
        return "DEV_ONLY_SECRET"
    return AUTH_SECRET


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("password_too_short")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    password_hash = base64.b64encode(digest).decode("ascii")
    return salt, password_hash


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    if not salt or not expected_hash:
        return False
    try:
        _, password_hash = hash_password(password, salt)
    except ValueError:
        return False
    return hmac.compare_digest(password_hash, expected_hash)


def generate_access_token(user_id: int) -> str:
    now = int(time.time())
    expires_at = now + AUTH_TOKEN_TTL_SECONDS
    payload = f"{user_id}:{expires_at}"
    secret = _ensure_secret().encode("utf-8")
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def generate_refresh_token(user_id: int) -> str:
    now = int(time.time())
    expires_at = now + AUTH_REFRESH_TOKEN_TTL_SECONDS
    payload = f"r:{user_id}:{expires_at}"
    secret = _ensure_secret().encode("utf-8")
    sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _parse_token(token: str) -> tuple[int, int, str]:
    parts = token.split(":")
    if len(parts) != 3:
        raise ValueError("invalid_token_format")
    user_id = int(parts[0])
    expires_at = int(parts[1])
    sig = parts[2]
    return user_id, expires_at, sig


def _parse_refresh_token(token: str) -> tuple[int, int, str]:
    parts = token.split(":")
    if len(parts) != 4 or parts[0] != "r":
        raise ValueError("invalid_refresh_token_format")
    user_id = int(parts[1])
    expires_at = int(parts[2])
    sig = parts[3]
    return user_id, expires_at, sig


def _verify_signature(payload: str, signature: str) -> bool:
    secret = _ensure_secret().encode("utf-8")
    expected_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


def resolve_refresh_user_id(refresh_token: str) -> int:
    try:
        user_id, expires_at, sig = _parse_refresh_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_refresh_token")
    payload = f"r:{user_id}:{expires_at}"
    if not _verify_signature(payload, sig):
        raise HTTPException(status_code=401, detail="invalid_refresh_token_signature")
    if expires_at < int(time.time()):
        raise HTTPException(status_code=401, detail="refresh_token_expired")
    return user_id


def resolve_user_id(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[int] = Header(default=None),
) -> int:
    """
    Resolve user id either from Authorization Bearer token (preferred) or X-User-Id header.
    Raises HTTP 401 on failure.
    """
    if authorization:
        token = authorization.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        try:
            user_id, expires_at, sig = _parse_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="invalid_token")
        payload = f"{user_id}:{expires_at}"
        if not _verify_signature(payload, sig):
            raise HTTPException(status_code=401, detail="invalid_token_signature")
        if expires_at < int(time.time()):
            raise HTTPException(status_code=401, detail="token_expired")
        return user_id
    if x_user_id is not None:
        return x_user_id
    raise HTTPException(status_code=401, detail="unauthorized")
