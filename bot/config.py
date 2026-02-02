from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass
class Config:
    bot_token: str
    api_base_url: str
    default_lang: str
    default_timezone: str
    default_currency: str
    webhook_url: str
    webhook_host: str
    webhook_port: int
    internal_host: str
    internal_port: int
    internal_token: str
    state_path: str
    log_level: str


def build_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required to start the bot.")

    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    parsed = urlsplit(webhook_url) if webhook_url else None
    webhook_host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    webhook_port = int(os.getenv("WEBHOOK_PORT", parsed.port if parsed and parsed.port else 8081))
    internal_host = os.getenv("BOT_INTERNAL_HOST", "0.0.0.0")
    internal_port = int(os.getenv("BOT_INTERNAL_PORT", "7090"))
    internal_token = os.getenv("BOT_INTERNAL_TOKEN", "").strip()
    state_path = os.getenv("BOT_STATE_PATH", "data/bot_state.json")

    return Config(
        bot_token=token,
        api_base_url=os.getenv("API_BASE_URL", "http://api:8000/v1").rstrip("/"),
        default_lang=os.getenv("DEFAULT_LANG", "zh-CN"),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
        default_currency=os.getenv("DEFAULT_CURRENCY", "CNY"),
        webhook_url=webhook_url,
        webhook_host=webhook_host,
        webhook_port=webhook_port,
        internal_host=internal_host,
        internal_port=internal_port,
        internal_token=internal_token,
        state_path=state_path,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
