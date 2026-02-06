from __future__ import annotations

import os
from urllib.parse import urlencode

from fastapi import HTTPException


EMAIL_VERIFICATION_ENABLED = os.getenv("EMAIL_VERIFICATION_ENABLED", "true").lower() == "true"
PASSWORD_RESET_URL = os.getenv("PASSWORD_RESET_URL", "http://localhost:3000/reset-password")
EMAIL_VERIFICATION_URL = os.getenv("EMAIL_VERIFICATION_URL", "http://localhost:3000/verify-email")
LOCAL_EMAIL_STORE_PATH = os.getenv("LOCAL_EMAIL_STORE_PATH", "/data/local_emails.log")


def _build_link(base_url: str, token: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}{urlencode({'token': token})}"


def _persist_message(subject: str, to_email: str, link: str) -> None:
    try:
        with open(LOCAL_EMAIL_STORE_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"TO={to_email}\nSUBJECT={subject}\nLINK={link}\n---\n")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="local_email_persist_failed") from exc


def send_verification_email(to_email: str, token: str) -> None:
    if not EMAIL_VERIFICATION_ENABLED:
        return
    link = _build_link(EMAIL_VERIFICATION_URL, token)
    _persist_message("Verify your email", to_email, link)


def send_password_reset_email(to_email: str, token: str) -> None:
    if not EMAIL_VERIFICATION_ENABLED:
        return
    link = _build_link(PASSWORD_RESET_URL, token)
    _persist_message("Reset your password", to_email, link)
