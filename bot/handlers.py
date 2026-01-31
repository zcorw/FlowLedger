from __future__ import annotations

from typing import Optional, Any, List, Tuple
from pathlib import Path
import asyncio
from uuid import uuid4

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

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


def _extract_ocr_fields(result: dict[str, Any]) -> dict[str, Any]:
    def pick(*keys: str) -> Any:
        for key in keys:
            if key in result:
                return result[key]
        return None

    return {
        "name": pick("name", "消费名称", "娑堣垂鍚嶇О"),
        "amount": pick("amount", "消费金额", "娑堣垂閲戦"),
        "type": pick("type", "消费分类", "娑堣垂鍒嗙被"),
        "merchant": pick("merchant", "消费商家名称", "娑堣垂鍟嗗鍚嶇О"),
        "occurred_at": pick("occurred_at", "消费时间", "娑堣垂鏃堕棿"),
    }


def _guess_content_type(suffix: str) -> str:
    ext = suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    if ext == ".gif":
        return "image/gif"
    return "application/octet-stream"


def _receipt_preview(payload: dict[str, Any]) -> str:
    return (
        "OCR result:\n"
        f"- Name: {payload.get('name')}\n"
        f"- Amount: {payload.get('amount')} {payload.get('currency')}\n"
        f"- Merchant: {payload.get('merchant')}\n"
        f"- Time: {payload.get('occurred_at')}\n"
        f"- Category: {payload.get('_category_name')}\n"
        f"- Note: {payload.get('note')}\n"
        "Edit any field or confirm to save."
    )


def _receipt_keyboard(receipt_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Edit Name", callback_data=f"receipt_edit:name:{receipt_id}"),
                InlineKeyboardButton(text="Edit Amount", callback_data=f"receipt_edit:amount:{receipt_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="Edit Merchant", callback_data=f"receipt_edit:merchant:{receipt_id}"
                ),
                InlineKeyboardButton(text="Edit Time", callback_data=f"receipt_edit:occurred_at:{receipt_id}"),
            ],
            [
                InlineKeyboardButton(
                    text="Edit Category", callback_data=f"receipt_edit:category:{receipt_id}"
                ),
                InlineKeyboardButton(text="Edit Currency", callback_data=f"receipt_edit:currency:{receipt_id}"),
            ],
            [
                InlineKeyboardButton(text="Edit Note", callback_data=f"receipt_edit:note:{receipt_id}"),
            ],
            [
                InlineKeyboardButton(text="Confirm", callback_data=f"receipt_confirm:{receipt_id}"),
                InlineKeyboardButton(text="Cancel", callback_data=f"receipt_cancel:{receipt_id}"),
            ],
        ]
    )

async def get_categories(token: str) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
    svc = get_service()
    return await svc.list_categories(token)

@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    text = (message.text or "").split(maxsplit=2)
    if len(text) < 3:
        await message.answer("Usage: /start <username> <password>")
        return

    username = text[1].strip()
    password = text[2].strip()
    user_id, err = await svc.login_and_link(user.id if user else None, username, password)
    if not user_id:
        await message.answer(f"Unable to link your account: {err}")
        return

    token, token_err = await svc.get_cached_token(user.id if user else None)
    if not token:
        await message.answer(f"Unable to load preferences: {token_err}")
        return

    prefs, _ = await svc.fetch_preferences(token)
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
        "/start <username> <password> - link to an existing account\n"
        "/help - show this help message\n"
        "/me - show your user id and preferences\n"
        "Send a receipt photo to OCR and save an expense\n"
        "/link &lt;token&gt; - link to an existing Flow-Ledger account\n"
        "/set currency|timezone|lang &lt;value&gt; - update your defaults"
    )


@router.message(Command("me"))
async def handle_me(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    token, err = await svc.get_cached_token(user.id if user else None)
    if not token:
        await message.answer(f"Unable to load your profile: {err}")
        return

    me, err_user = await svc.fetch_user(token)
    prefs, err_pref = await svc.fetch_preferences(token)
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
    token, err = await svc.get_cached_token(user.id if user else None)
    if not token:
        await message.answer(f"Unable to prepare linking: {err}")
        return

    text = (message.text or "").split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Usage: /link &lt;token&gt;")
        return

    link_token = text[1].strip()
    data, link_err = await svc.link_user_with_token(
        token, user.id if user else 0, link_token=link_token
    )
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
    token, err = await svc.get_cached_token(user.id if user else None)
    if not token:
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

    updated, update_err = await svc.update_preference(token, field_map[field_key], value)
    if update_err:
        await message.answer(update_err)
        return

    await message.answer(
        "Preferences updated:\n"
        f"- base_currency: {updated.get('base_currency')}\n"
        f"- timezone: {updated.get('timezone')}\n"
        f"- language: {updated.get('language')}"
    )


@router.message(F.photo)
async def handle_receipt_photo(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    token, err = await svc.get_cached_token(user.id if user else None)
    if not token:
        await message.answer(f"Unable to process receipt: {err}")
        return

    photo = message.photo[-1]
    tg_file = await message.bot.get_file(photo.file_id)
    suffix = Path(tg_file.file_path or "").suffix or ".jpg"
    filename = f"{photo.file_unique_id}{suffix}"
    content_type = _guess_content_type(suffix)
    file_obj = await message.bot.download(tg_file)
    if not file_obj:
        await message.answer("Failed to download the photo from Telegram.")
        return
    file_obj.seek(0)
    content = file_obj.read()

    await message.answer("Receipt received. Running OCR, please wait...")

    async def _process() -> None:
        upload_resp, upload_err = await svc.upload_receipt(
            token, filename, content_type, content
        )
        if not upload_resp:
            await message.answer(upload_err or "Receipt upload failed.")
            return

        task_id = upload_resp.get("task_id")
        if not task_id:
            await message.answer("Receipt upload succeeded but task_id is missing.")
            return

        for _ in range(15):
            task, task_err = await svc.fetch_receipt_task(token, task_id)
            if not task:
                await message.answer(task_err or "Failed to fetch OCR result.")
                return
            if task.get("status") == "succeeded":
                result = task.get("result") or {}
                fields = _extract_ocr_fields(result)
                prefs, _ = await svc.fetch_preferences(token)
                currency = (prefs or {}).get("base_currency")
                categories, _ = await svc.list_categories(token)
                category_id = None
                if categories and fields.get("type"):
                    for cat in categories:
                        if cat.get("name") == fields.get("type"):
                            category_id = cat.get("id")
                            break

                receipt_id = str(uuid4())
                payload = {
                    "name": fields.get("name") or "Receipt expense",
                    "amount": fields.get("amount"),
                    "currency": currency or "USD",
                    "category_id": category_id,
                    "file_id": upload_resp.get("file_id"),
                    "merchant": fields.get("merchant"),
                    "occurred_at": fields.get("occurred_at"),
                    "note": "Imported from receipt OCR",
                    "_category_name": fields.get("type"),
                }
                await svc.state.set_pending_receipt(user.id if user else 0, receipt_id, payload)

                await message.answer(_receipt_preview(payload), reply_markup=_receipt_keyboard(receipt_id))
                return
            if task.get("status") == "failed":
                await message.answer("OCR failed. Please try another image.")
                return
            await asyncio.sleep(2)

        await message.answer("OCR is taking too long. Please try again later.")

    asyncio.create_task(_process())


@router.callback_query(F.data.startswith("receipt_confirm:"))
async def handle_receipt_confirm(callback: CallbackQuery) -> None:
    svc = get_service()
    user = callback.from_user
    token, err = await svc.get_cached_token(user.id if user else None)
    if not token:
        await callback.answer("Please /start <username> <password> first.")
        return

    receipt_id = (callback.data or "").split(":", 1)[-1]
    payload = await svc.state.get_pending_receipt(user.id if user else 0, receipt_id)
    if not payload:
        await callback.answer("This receipt request has expired.")
        return

    payload_to_send = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    created, create_err = await svc.create_expense(token, payload_to_send)
    if create_err:
        await callback.answer("Failed to save expense.")
        await callback.message.answer(create_err)
        return

    await svc.state.clear_pending_receipt(user.id if user else 0, receipt_id)
    await callback.answer("Saved.")
    await callback.message.answer(
        f"Expense saved: {created.get('name')} {created.get('amount')} {created.get('currency')}"
    )


@router.callback_query(F.data.startswith("receipt_cancel:"))
async def handle_receipt_cancel(callback: CallbackQuery) -> None:
    svc = get_service()
    user = callback.from_user
    receipt_id = (callback.data or "").split(":", 1)[-1]
    await svc.state.clear_pending_receipt(user.id if user else 0, receipt_id)
    await callback.answer("Cancelled.")
    await callback.message.answer("Receipt import cancelled.")


@router.callback_query(F.data.startswith("receipt_edit:"))
async def handle_receipt_edit(callback: CallbackQuery) -> None:
    svc = get_service()
    user = callback.from_user
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer("Invalid edit request.")
        return
    field, receipt_id = parts[1], parts[2]
    payload = await svc.state.get_pending_receipt(user.id if user else 0, receipt_id)
    if not payload:
        await callback.answer("This receipt request has expired.")
        return

    payload["_awaiting_field"] = field
    await svc.state.set_pending_receipt(user.id if user else 0, receipt_id, payload)
    await svc.state.set_active_receipt_edit(user.id if user else 0, receipt_id)
    await callback.answer()
    if field == "category":
        token, err = await svc.get_cached_token(user.id)
        if not token:
            await callback.message.answer(err or "Missing token.")
            return
        categories, cat_err = await get_categories(token)
        if cat_err:
            await callback.message.answer(cat_err)
        else:
            cat_list = "\n".join(c.get("name") for c in categories)
            await callback.message.answer(
                f"Send new category name for the receipt. Available categories:\n{cat_list}"
            )
    else:
        await callback.message.answer(f"Send new value for {field}.")


@router.message(F.text)
async def handle_receipt_edit_text(message: Message) -> None:
    svc = get_service()
    user = message.from_user
    if not user or not message.text:
        return
    if message.text.strip().startswith("/"):
        return

    receipt_id = await svc.state.get_active_receipt_edit(user.id)
    if not receipt_id:
        return

    payload = await svc.state.get_pending_receipt(user.id, receipt_id)
    if not payload:
        await svc.state.set_active_receipt_edit(user.id, None)
        return

    field = payload.get("_awaiting_field")
    if not field:
        await svc.state.set_active_receipt_edit(user.id, None)
        return

    value = message.text.strip()
    if field == "amount":
        try:
            float(value)
        except ValueError:
            await message.answer("Amount must be a number. Try again.")
            return
        payload["amount"] = value
    elif field == "currency":
        if len(value) != 3 or not value.isalpha():
            await message.answer("Currency must be a 3-letter code (e.g., USD).")
            return
        payload["currency"] = value.upper()
    elif field == "occurred_at":
        payload["occurred_at"] = value
    elif field == "merchant":
        payload["merchant"] = value
    elif field == "name":
        payload["name"] = value
    elif field == "note":
        payload["note"] = None if value == "-" else value
    elif field == "category":
        token, err = await svc.get_cached_token(user.id)
        if not token:
            await message.answer(err or "Missing token.")
            return
        categories, cat_err = await get_categories(token)
        if cat_err:
            await message.answer(cat_err)
            return
        match = next((c for c in categories if c.get("name") == value), None)
        if not match:
            await message.answer("Category not found. Use exact category name.")
            return
        payload["category_id"] = match.get("id")
        payload["_category_name"] = match.get("name")
    else:
        await message.answer("Unknown field.")
        return

    payload["_awaiting_field"] = None
    await svc.state.set_pending_receipt(user.id, receipt_id, payload)
    await svc.state.set_active_receipt_edit(user.id, None)
    await message.answer(_receipt_preview(payload), reply_markup=_receipt_keyboard(receipt_id))
