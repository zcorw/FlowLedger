from __future__ import annotations

from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from service import BotService


router = Router()
_service: Optional[BotService] = None


def set_service(service: BotService) -> None:
    global _service
    _service = service


def get_service() -> BotService:
    if not _service:
        raise RuntimeError("Bot service is not initialized.")
    return _service


@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    user_id, err = await svc.ensure_user(user.id if user else None)
    if not user_id:
        await message.answer(f"Unable to initialize your account: {err}")
        return

    prefs, _ = await svc.fetch_preferences(user_id)
    greeting = "Welcome to Flow-Ledger bot!"
    if user and user.first_name:
        greeting = f"Welcome, {user.first_name}!"
    prefs_line = (
        f"Base currency: {prefs.get('base_currency')}, "
        f"Timezone: {prefs.get('timezone')}, "
        f"Language: {prefs.get('language')}"
        if prefs
        else "Preferences not available."
    )
    await message.answer(
        f"{greeting}\n"
        f"Use /help to see available commands.\n"
        f"{prefs_line}"
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Available commands:\n"
        "/start - initialize and link your account\n"
        "/help - show this help message\n"
        "/me - show your user id and preferences\n"
        "/link &lt;token&gt; - link to an existing Flow-Ledger account\n"
        "/set currency|timezone|lang &lt;value&gt; - update your defaults"
    )


@router.message(Command("me"))
async def handle_me(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    user_id, err = await svc.ensure_user(user.id if user else None)
    if not user_id:
        await message.answer(f"Unable to load your profile: {err}")
        return

    me, err_user = await svc.fetch_user(user_id)
    prefs, err_pref = await svc.fetch_preferences(user_id)
    if err_user:
        await message.answer(err_user)
        return
    if err_pref:
        await message.answer(err_pref)
        return

    await message.answer(
        "Your account:\n"
        f"- user_id: {me.get('id')}\n"
        f"- telegram_user_id: {me.get('telegram_user_id')}\n"
        f"- base_currency: {prefs.get('base_currency')}\n"
        f"- timezone: {prefs.get('timezone')}\n"
        f"- language: {prefs.get('language')}"
    )


@router.message(Command("link"))
async def handle_link(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    user_id, err = await svc.ensure_user(user.id if user else None)
    if not user_id:
        await message.answer(f"Unable to prepare linking: {err}")
        return

    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Usage: /link &lt;token&gt;")
        return

    link_token = text[1].strip()
    data, link_err = await svc.link_user(user_id, user.id if user else 0, link_token=link_token)
    if link_err:
        await message.answer(link_err)
        return

    await message.answer(
        f"Linked successfully.\n"
        f"user_id: {data.get('id')}\n"
        f"telegram_user_id: {data.get('telegram_user_id')}"
    )


@router.message(Command("set"))
async def handle_set(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    user_id, err = await svc.ensure_user(user.id if user else None)
    if not user_id:
        await message.answer(f"Unable to update preferences: {err}")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: /set currency|timezone|lang &lt;value&gt;")
        return

    field_key = parts[1].lower()
    value = parts[2].strip()
    field_map = {"currency": "base_currency", "timezone": "timezone", "lang": "language"}
    if field_key not in field_map:
        await message.answer("Unknown field. Use currency, timezone, or lang.")
        return

    updated, update_err = await svc.update_preference(user_id, field_map[field_key], value)
    if update_err:
        await message.answer(update_err)
        return

    await message.answer(
        "Preferences updated:\n"
        f"- base_currency: {updated.get('base_currency')}\n"
        f"- timezone: {updated.get('timezone')}\n"
        f"- language: {updated.get('language')}"
    )
