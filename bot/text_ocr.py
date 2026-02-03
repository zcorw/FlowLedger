from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class TextOcrError(RuntimeError):
    pass


def _extract_output_text(payload: Dict[str, Any]) -> Optional[str]:
    text = payload.get("output_text")
    if text:
        return text
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"}:
                return content.get("text")
    return None


async def recognize_receipt_text(text: str, categories: List[str]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise TextOcrError("missing_openai_api_key")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
    timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))

    category_list = ", ".join(categories) if categories else "other"

    prompt = (
        "You are a receipt summarization engine.\n"
        "Hard constraints (must follow):\n"
        "- Output ONLY valid JSON. No markdown, no explanations.\n"
        "- Produce EXACTLY ONE summary record.\n"
        "- ALL fields are REQUIRED. Do NOT output null or empty values.\n"
        "- If information is unclear, infer the most reasonable value from the receipt context.\n"
        "- Do not invent merchants, prices, or dates not supported by the receipt.\n"
        "- amount must be the final total actually paid by the customer.\n"
        "- currency must be an ISO 4217 code (e.g., CNY, JPY, USD).\n"
        "- If the receipt has an explicit currency unit, use it.\n"
        "- If the currency symbol is ambiguous, infer by the receipt language.\n"
        "- occurred_at must be ISO 8601 format. Include timezone if the receipt implies one.\n"
        f"- type must be one of: {category_list}.\n"
        "- name must be a concise, human-readable summary of the entire purchase.\n"
        "\n"
        "Receipt text:\n"
        f"{text}"
    )

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "amount": {"type": "number"},
            "currency": {"type": "string"},
            "type": {"type": "string"},
            "merchant": {"type": "string"},
            "occurred_at": {"type": "string"},
        },
        "required": ["name", "amount", "currency", "type", "merchant", "occurred_at"],
    }

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "receipt_text_extract",
                "schema": schema,
            }
        },
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(api_url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.error(
                "OpenAI request failed: status=%s body=%s",
                resp.status_code,
                resp.text[:2000],
            )
            raise TextOcrError("openai_request_failed")
        data = resp.json()

    text_output = _extract_output_text(data)
    if not text_output:
        raise TextOcrError("openai_response_missing_text")
    try:
        result = json.loads(text_output)
    except json.JSONDecodeError as exc:
        raise TextOcrError("openai_response_invalid_json") from exc
    if not isinstance(result, dict):
        raise TextOcrError("openai_response_invalid_payload")
    return result

