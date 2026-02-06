from __future__ import annotations

import os

from fastapi import HTTPException

from .email_service import send_password_reset_email as send_password_reset_email_sendgrid
from .email_service import send_verification_email as send_verification_email_sendgrid
from .local_email_service import send_password_reset_email as send_password_reset_email_local
from .local_email_service import send_verification_email as send_verification_email_local


EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "sendgrid").lower()


def send_verification_email(to_email: str, token: str) -> None:
    if EMAIL_PROVIDER == "local":
        send_verification_email_local(to_email, token)
        return
    if EMAIL_PROVIDER == "sendgrid":
        send_verification_email_sendgrid(to_email, token)
        return
    raise HTTPException(status_code=500, detail="email_provider_not_supported")


def send_password_reset_email(to_email: str, token: str) -> None:
    if EMAIL_PROVIDER == "local":
        send_password_reset_email_local(to_email, token)
        return
    if EMAIL_PROVIDER == "sendgrid":
        send_password_reset_email_sendgrid(to_email, token)
        return
    raise HTTPException(status_code=500, detail="email_provider_not_supported")
