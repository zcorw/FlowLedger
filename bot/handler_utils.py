from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, User


def user_id_or_none(user: Optional[User]) -> Optional[int]:
    return user.id if user else None


def user_id_or_zero(user: Optional[User]) -> int:
    return user.id if user else 0


async def get_cached_token_or_reply(
    svc: Any,
    reply: Callable[[str], Awaitable[Any]],
    error_prefix: str,
) -> Optional[str]:
    token, err = await svc.get_cached_token()
    if not token:
        if err:
            await reply(f"{error_prefix}: {err}")
        else:
            await reply(error_prefix)
        return None
    return token


def extract_ocr_fields(result: dict[str, Any]) -> dict[str, Any]:
    def pick(*keys: str) -> Any:
        for key in keys:
            if key in result:
                return result[key]
        return None

    return {
        "name": pick("name", "消费名称"),
        "amount": pick("amount", "消费金额"),
        "currency": pick("currency", "币种"),
        "type": pick("type", "消费分类"),
        "institution": pick("institution", "消费账户"),
        "merchant": pick("merchant", "消费商家名称"),
        "occurred_at": pick("occurred_at", "消费时间"),
    }


def guess_content_type(suffix: str) -> str:
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


def receipt_preview(payload: dict[str, Any]) -> str:
    return (
        "OCR result:\n"
        f"- Name: {payload.get('name')}\n"
        f"- Amount: {payload.get('amount')} {payload.get('currency')}\n"
        f"- Merchant: {payload.get('merchant')}\n"
        f"- Time: {payload.get('occurred_at')}\n"
        f"- Category: {payload.get('_category_name')}\n"
        f"- Institution: {payload.get('_institution_name')}\n"
        f"- Note: {payload.get('note')}\n"
        "Edit any field or confirm to save."
    )


def receipt_keyboard(receipt_id: str) -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(
                    text="Edit Institution", callback_data=f"receipt_edit:institution:{receipt_id}"
                ),
                InlineKeyboardButton(text="Edit Note", callback_data=f"receipt_edit:note:{receipt_id}"),
            ],
            [
                InlineKeyboardButton(text="Confirm", callback_data=f"receipt_confirm:{receipt_id}"),
                InlineKeyboardButton(text="Cancel", callback_data=f"receipt_cancel:{receipt_id}"),
            ],
        ]
    )
