from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from aiogram import Bot

from config import Config


def _is_authorized(request: web.Request, config: Config) -> bool:
    if not config.internal_token:
        return True
    token = request.headers.get("X-Internal-Token", "").strip()
    return token == config.internal_token


async def _handle_notify(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    bot: Bot = request.app["bot"]
    if not _is_authorized(request, config):
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    telegram_user_id = payload.get("telegram_user_id")
    text = payload.get("text")
    if not isinstance(telegram_user_id, int) or not text:
        return web.json_response({"ok": False, "error": "missing_fields"}, status=422)

    try:
        await bot.send_message(chat_id=telegram_user_id, text=text)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to send telegram message: %s", exc)
        return web.json_response({"ok": False, "error": "send_failed"}, status=502)

    return web.json_response({"ok": True})


async def start_internal_server(bot: Bot, config: Config) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app["config"] = config
    app.router.add_post("/internal/notify", _handle_notify)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=config.internal_host, port=config.internal_port)
    await site.start()
    logging.info(
        "Internal notify server running at http://%s:%s",
        config.internal_host,
        config.internal_port,
    )
    return runner
