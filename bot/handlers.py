from __future__ import annotations

from typing import Optional, Any, Callable, Awaitable
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import asyncio
import httpx
from uuid import uuid4

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from service import BotService
from handler_utils import (
    extract_ocr_fields,
    get_cached_token_or_reply,
    guess_content_type,
    receipt_keyboard,
    receipt_preview,
    category_keyboard,
    institution_keyboard,
    user_id_or_none,
    user_id_or_zero,
)


router = Router()
_service: Optional[BotService] = None


def set_service(service: BotService) -> None:
    global _service
    _service = service


def get_service() -> BotService:
    if not _service:
        raise RuntimeError("Bot service is not initialized.")
    return _service

class FetchError(Exception):
    pass

async def svc_request(token: str, request_builder: Callable[[str], Awaitable[httpx.Response]], *args, **kwargs) -> Optional[dict[str, Any]]:
    result, err = await request_builder(token, *args, **kwargs)
    if err:
        raise FetchError(err)
    return result

async def set_receipt(user: Any, message: Message, receipt_id: str, svc: BotService, edit_payload: Callable[[str], Awaitable[dict[str, Any]]]) -> None:
    payload = await svc.state.get_pending_receipt(user.id, receipt_id)
    if not payload:
        await svc.state.set_active_receipt_edit(user.id, None)
        return

    field = payload.get("_awaiting_field")
    if not field:
        await svc.state.set_active_receipt_edit(user.id, None)
        return
    
    try:
        _payload = await edit_payload(field)
    except ValueError as ve:
        await message.answer(str(ve))
        return
    except FetchError as fe:
        await message.answer(str(fe))
        return
    payload.update(_payload)
    
    payload["_awaiting_field"] = None
    await svc.state.set_pending_receipt(user.id, receipt_id, payload)
    await svc.state.set_active_receipt_edit(user.id, None)
    await message.answer(receipt_preview(payload), reply_markup=receipt_keyboard(receipt_id))

async def set_receipt_command(callback: CallbackQuery, svc_request: Callable[[BotService, str, str], Awaitable[dict[str, Any]]]) -> None:
    user = callback.from_user
    svc = get_service().with_user(user_id_or_none(user))
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer("Invalid edit request.")
        return
    token = await get_cached_token_or_reply(
        svc, callback.message.answer, "Unable to process receipt text"
    )
    if not token:
        return
    category_id, receipt_id = parts[1], parts[2]
    async def payload_editor(field: str) -> Awaitable[dict[str, Any]]:
        return await svc_request(svc, token, category_id)
    
    
    await set_receipt(user, callback.message, receipt_id, svc, payload_editor)


@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    base_svc = get_service()
    user = message.from_user
    svc = base_svc.with_user(user_id_or_none(user))
    text = (message.text or "").split(maxsplit=2)
    if len(text) < 3:
        await message.answer("Usage: /start &lt;username&gt; &lt;password&gt;")
        return

    username = text[1].strip()
    password = text[2].strip()
    user_id, err = await base_svc.login_and_link(user_id_or_none(user), username, password)
    if not user_id:
        await message.answer(f"Unable to link your account: {err}")
        return

    token = await get_cached_token_or_reply(
        svc, message.answer, "Unable to load preferences"
    )
    if not token:
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
        "/start &lt;username&gt; &lt;password&gt; - link to an existing account\n"
        "/help - show this help message\n"
        "/me - show your user id and preferences\n"
        "Send a receipt photo to OCR and save an expense\n"
    )


@router.message(Command("me"))
async def handle_me(message: Message) -> None:
    user = message.from_user
    svc = get_service().with_user(user_id_or_none(user))
    token = await get_cached_token_or_reply(
        svc, message.answer, "Unable to load your profile"
    )
    if not token:
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

@router.message(F.photo)
async def handle_receipt_photo(message: Message) -> None:
    user = message.from_user
    svc = get_service().with_user(user_id_or_none(user))
    token = await get_cached_token_or_reply(
        svc, message.answer, "Unable to process receipt"
    )
    if not token:
        return

    photo = message.photo[-1]
    tg_file = await message.bot.get_file(photo.file_id)
    suffix = Path(tg_file.file_path or "").suffix or ".jpg"
    filename = f"{photo.file_unique_id}{suffix}"
    content_type = guess_content_type(suffix)
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
                fields = extract_ocr_fields(result)
                prefs, _ = await svc.fetch_preferences(token)
                currency = fields.get("currency") or (prefs or {}).get("base_currency")
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
                    "_institution_name": fields.get("institution"),
                }
                await svc.state.set_pending_receipt(user_id_or_zero(user), receipt_id, payload)

                await message.answer(receipt_preview(payload), reply_markup=receipt_keyboard(receipt_id))
                return
            if task.get("status") == "failed":
                await message.answer("OCR failed. Please try another image.")
                return
            await asyncio.sleep(2)

        await message.answer("OCR is taking too long. Please try again later.")

    asyncio.create_task(_process())


@router.callback_query(F.data.startswith("receipt_confirm:"))
async def handle_receipt_confirm(callback: CallbackQuery) -> None:
    user = callback.from_user
    svc = get_service().with_user(user_id_or_none(user))
    token, err = await svc.get_cached_token()
    if not token:
        await callback.answer("Please /start &lt;username&gt; &lt;password&gt; first.")
        return

    receipt_id = (callback.data or "").split(":", 1)[-1]
    payload = await svc.state.get_pending_receipt(user_id_or_zero(user), receipt_id)
    if not payload:
        await callback.answer("This receipt request has expired.")
        return

    payload_to_send = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    created, create_err = await svc.create_expense(token, payload_to_send)
    if create_err:
        await callback.answer("Failed to save expense.")
        await callback.message.answer(create_err)
        return

    await svc.state.clear_pending_receipt(user_id_or_zero(user), receipt_id)
    monthly_result, err = await svc.getMonthlyExpenseSummary(token)
    summary = Decimal(monthly_result.get("current_total")).quantize(
        Decimal("0.00"),
        rounding=ROUND_HALF_UP
    )
    if err:
        await callback.message.answer(f"Expense saved, but failed to fetch monthly summary: {err}")
    await callback.answer("Saved.")
    await callback.message.answer(
        f"Expense saved: {created.get('name')} {created.get('amount')} {created.get('currency')},\n"
        f"Your total expenses this month: {summary} {monthly_result.get('currency')}."
    )


@router.callback_query(F.data.startswith("receipt_cancel:"))
async def handle_receipt_cancel(callback: CallbackQuery) -> None:
    user = callback.from_user
    svc = get_service().with_user(user_id_or_none(user))
    receipt_id = (callback.data or "").split(":", 1)[-1]
    await svc.state.clear_pending_receipt(user_id_or_zero(user), receipt_id)
    await callback.answer("Cancelled.")
    await callback.message.answer("Receipt import cancelled.")


@router.callback_query(F.data.startswith("receipt_edit:"))
async def handle_receipt_edit(callback: CallbackQuery) -> None:
    user = callback.from_user
    svc = get_service().with_user(user_id_or_none(user))
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer("Invalid edit request.")
        return
    field, receipt_id = parts[1], parts[2]
    payload = await svc.state.get_pending_receipt(user_id_or_zero(user), receipt_id)
    if not payload:
        await callback.answer("This receipt request has expired.")
        return

    payload["_awaiting_field"] = field
    await svc.state.set_pending_receipt(user_id_or_zero(user), receipt_id, payload)
    await svc.state.set_active_receipt_edit(user_id_or_zero(user), receipt_id)
    await callback.answer()
    token = await get_cached_token_or_reply(
        svc, callback.message.answer, "Missing token"
    )
    if field == "category":
        if not token:
            return
        try:
            categories = await svc_request(token, lambda t: svc.list_categories(t))
        except FetchError as cat_err:
            await callback.message.answer(cat_err)
            return
        cat_list = "\n".join(c.get("name") for c in categories)
        await callback.message.answer(
            f"Send new category name for the receipt. Available categories:\n{cat_list}"
        )
    elif field == "institution":
        if not token:
            return
        try:
            institutions = await svc_request(token, lambda t: svc.list_institutions(t))
        except FetchError as inst_err:
            await callback.message.answer(inst_err)
            return
        inst_list = "\n".join(i.get("name") for i in institutions)
        await callback.message.answer(
            f"Send new institution name for the receipt. Available institutions:\n{inst_list}"
        )
    elif field == "cat_btn":
        if not token:
            return
        try:
            most_categories = await svc_request(token, lambda t: svc.most_recent_categories(t))
        except FetchError as cat_err:
            await callback.message.answer(cat_err)
            return
        await callback.message.answer(
            "Select new category for the receipt:",
            reply_markup=category_keyboard(most_categories, receipt_id),
        )
    elif field == "ins_btn":
        if not token:
            return
        try:
            most_institutions = await svc_request(token, lambda t: svc.most_recent_institutions(t))
        except FetchError as inst_err:
            await callback.message.answer(inst_err)
            return
        await callback.message.answer(
            "Select new institution for the receipt:",
            reply_markup=institution_keyboard(most_institutions, receipt_id),
        )
    else:
        await callback.message.answer(f"Send new value for {field}.")

@router.callback_query(F.data.startswith("set_catategory:"))
async def handle_set_category(callback: CallbackQuery) -> None:
    async def payload_editor(svc: BotService, token: str, category_id: str) -> Awaitable[dict[str, Any]]:
        payload: dict[str, Any] = {}
        categories = await svc_request(token, lambda t: svc.list_categories(t))
        match = next((c for c in categories if c.get("id") == int(category_id)), None)
        if not match:
            raise ValueError("Category not found.")
        payload["category_id"] = match.get("id")
        payload["_category_name"] = match.get("name")
        return payload
    await set_receipt_command(callback, payload_editor)

@router.callback_query(F.data.startswith("set_institution:"))
async def handle_set_institution(callback: CallbackQuery) -> None:
    async def payload_editor(svc: BotService, token: str, institution_id: str) -> Awaitable[dict[str, Any]]:
        payload: dict[str, Any] = {}
        institutions = await svc_request(token, lambda t: svc.list_institutions(t))
        match = next((i for i in institutions if i.get("id") == int(institution_id)), None)
        if not match:
            raise ValueError("Institution not found.")
        payload["paid_account_id"] = match.get("id")
        payload["_institution_name"] = match.get("name")
        return payload
    await set_receipt_command(callback, payload_editor)

@router.message(F.text)
async def handle_receipt_edit_text(message: Message) -> None:
    user = message.from_user
    svc = get_service().with_user(user_id_or_none(user))
    if not user or not message.text:
        return
    text = message.text.strip()
    if text.startswith("/"):
        return

    token = await get_cached_token_or_reply(
        svc, message.answer, "Unable to process receipt text"
    )
    if not token:
        return
    receipt_id = await svc.state.get_active_receipt_edit(user.id)
    if not receipt_id:
        await message.answer("Text received. Running OCR, please wait...")

        async def _process_text() -> None:
            upload_resp, upload_err = await svc.upload_receipt_text(token, text)
            if not upload_resp:
                await message.answer(upload_err or "Text OCR upload failed.")
                return

            task_id = upload_resp.get("task_id")
            if not task_id:
                await message.answer("Text OCR upload succeeded but task_id is missing.")
                return

            for _ in range(15):
                task, task_err = await svc.fetch_receipt_text_task(token, task_id)
                if not task:
                    await message.answer(task_err or "Failed to fetch text OCR result.")
                    return
                if task.get("status") == "succeeded":
                    result = task.get("result") or {}
                    fields = extract_ocr_fields(result)
                    prefs, _ = await svc.fetch_preferences(token)
                    currency = fields.get("currency") or (prefs or {}).get("base_currency")
                    categories, _ = await svc.list_categories(token)
                    category_id = None
                    if categories and fields.get("type"):
                        for cat in categories:
                            if cat.get("name") == fields.get("type"):
                                category_id = cat.get("id")
                                break

                    receipt_id_local = str(uuid4())
                    payload = {
                        "name": fields.get("name") or "Receipt expense",
                        "amount": fields.get("amount"),
                        "currency": currency or "USD",
                        "category_id": category_id,
                        "merchant": fields.get("merchant"),
                        "occurred_at": fields.get("occurred_at"),
                        "note": "Imported from text OCR",
                        "_category_name": fields.get("type"),
                        "_institution_name": fields.get("institution"),
                    }
                    await svc.state.set_pending_receipt(
                        user_id_or_zero(user), receipt_id_local, payload
                    )
                    await message.answer(
                        receipt_preview(payload),
                        reply_markup=receipt_keyboard(receipt_id_local),
                    )
                    return
                if task.get("status") == "failed":
                    await message.answer("Text OCR failed. Please try again.")
                    return
                await asyncio.sleep(2)

            await message.answer("Text OCR is taking too long. Please try again later.")

        asyncio.create_task(_process_text())
        return

    value = message.text.strip()
    
    async def payload_editor(field: str) -> Awaitable[dict[str, Any]]:
        payload: dict[str, Any] = {}
        if field == "amount":
            try:
                float(value)
            except ValueError:
                raise ValueError("Amount must be a number. Try again.")
            payload["amount"] = value
        elif field == "currency":
            if len(value) != 3 or not value.isalpha():
                raise ValueError("Currency must be a 3-letter code (e.g., USD).")
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
            categories = await svc_request(token, lambda t: svc.list_categories(t))
            match = next((c for c in categories if c.get("name") == value), None)
            if not match:
                raise ValueError("Category not found. Use exact category name.")
            payload["category_id"] = match.get("id")
            payload["_category_name"] = match.get("name")
        elif field == "institution":
            institutions = await svc_request(token, lambda t: svc.list_institutions(t))
            match = next((i for i in institutions if i.get("name") == value), None)
            if not match:
                raise ValueError("Institution not found. Use exact institution name.")
            payload["paid_account_id"] = match.get("id")
            payload["_institution_name"] = match.get("name")
        else:
            raise ValueError("Unknown field.")
        return payload
    
    await set_receipt(user, message, receipt_id, svc, payload_editor)