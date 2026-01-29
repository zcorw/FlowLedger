from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ReceiptOcrError(RuntimeError):
    pass


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "application/octet-stream"


def _extract_output_text(payload: Dict[str, Any]) -> Optional[str]:
    text = payload.get("output_text")
    if text:
        return text
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"}:
                return content.get("text")
    return None


def recognize_receipt(image_path: Path, categories: List[str]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ReceiptOcrError("missing_openai_api_key")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))

    mime_type = _guess_mime_type(image_path)
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    category_list = ", ".join(categories) if categories else "其他"

    prompt = (
        "Extract receipt line items and return a JSON object only. "
        "Top-level fields must include: items, merchant, occurred_at. "
        "merchant is the receipt's merchant name or empty string if unavailable. "
        "occurred_at should be 'YYYY-MM-DD HH:MM' if available, otherwise empty string. "
        "Each item must include: name, amount, type. "
        "amount must be a number. "
        f"type must be one of: {category_list}."
    )

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "amount": {"type": "number"},
                        "type": {"type": "string"},
                    },
                    "required": ["name", "amount", "type"],
                },
            },
            "merchant": {"type": "string"},
            "occurred_at": {"type": "string"},
        },
        "required": ["items", "merchant", "occurred_at"],
    }

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{image_b64}",
                    },
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "receipt_extract",
                "schema": schema,
            }
        },
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.post(api_url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "OpenAI request failed: status=%s body=%s",
                resp.status_code,
                resp.text[:2000],
            )
            raise ReceiptOcrError("openai_request_failed")
        data = resp.json()

    text = _extract_output_text(data)
    if not text:
        raise ReceiptOcrError("openai_response_missing_text")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReceiptOcrError("openai_response_invalid_json") from exc
    if not isinstance(result, dict):
        raise ReceiptOcrError("openai_response_invalid_payload")
    return result
