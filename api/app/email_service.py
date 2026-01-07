from __future__ import annotations

import os
from urllib.parse import urlencode

from fastapi import HTTPException
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@example.com")
EMAIL_VERIFICATION_URL = os.getenv("EMAIL_VERIFICATION_URL", "http://localhost:3000/verify-email")
SENDGRID_VERIFICATION_TEMPLATE_ID = os.getenv("SENDGRID_VERIFICATION_TEMPLATE_ID")
EMAIL_VERIFICATION_ENABLED = os.getenv("EMAIL_VERIFICATION_ENABLED", "true").lower() == "true"


def _ensure_sendgrid_config():
    if not SENDGRID_API_KEY:
        raise HTTPException(status_code=500, detail="email_not_configured")
    if not SENDGRID_FROM_EMAIL:
        raise HTTPException(status_code=500, detail="email_from_not_configured")
    if not SENDGRID_VERIFICATION_TEMPLATE_ID:
        raise HTTPException(status_code=500, detail="email_template_not_configured")


def _build_verification_link(token: str) -> str:
    # Always append token as query parameter; callers should provide a base URL.
    sep = "&" if "?" in EMAIL_VERIFICATION_URL else "?"
    return f"{EMAIL_VERIFICATION_URL}{sep}{urlencode({'token': token})}"


def send_verification_email(to_email: str, token: str):
    """
    Send verification email via SendGrid. Raises HTTP 500 on configuration or delivery failure.
    """
    if not EMAIL_VERIFICATION_ENABLED:
        return
    _ensure_sendgrid_config()
    link = _build_verification_link(token)
    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=to_email,
        template_id=SENDGRID_VERIFICATION_TEMPLATE_ID,
    )
    message.dynamic_template_data = {
        "verification_url": link,
    }
    try:
        client = SendGridAPIClient(SENDGRID_API_KEY)
        client.send(message)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="failed_to_send_verification_email") from exc
