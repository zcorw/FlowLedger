from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional


class StateStore:
    """A tiny JSON file store for telegram_user_id -> user_id bindings."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {
            "telegram_to_user": {},
            "telegram_to_token": {},
            "pending_receipts": {},
            "active_receipt_edit": {},
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                # fall back to empty store if the file is corrupted
                self._data = {"telegram_to_user": {}}

    async def get_user_id(self, telegram_user_id: int) -> Optional[int]:
        async with self._lock:
            return self._data.get("telegram_to_user", {}).get(str(telegram_user_id))

    async def set_user_id(self, telegram_user_id: int, user_id: int) -> None:
        async with self._lock:
            self._data.setdefault("telegram_to_user", {})[str(telegram_user_id)] = user_id
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    async def get_token(self, telegram_user_id: int) -> Optional[str]:
        async with self._lock:
            return self._data.get("telegram_to_token", {}).get(str(telegram_user_id))

    async def set_token(self, telegram_user_id: int, token: str) -> None:
        async with self._lock:
            self._data.setdefault("telegram_to_token", {})[str(telegram_user_id)] = token
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    async def set_pending_receipt(
        self, telegram_user_id: int, receipt_id: str, payload: dict[str, Any]
    ) -> None:
        async with self._lock:
            bucket = self._data.setdefault("pending_receipts", {}).setdefault(
                str(telegram_user_id), {}
            )
            bucket[receipt_id] = payload
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    async def get_pending_receipt(
        self, telegram_user_id: int, receipt_id: str
    ) -> Optional[dict[str, Any]]:
        async with self._lock:
            return (
                self._data.get("pending_receipts", {})
                .get(str(telegram_user_id), {})
                .get(receipt_id)
            )

    async def clear_pending_receipt(self, telegram_user_id: int, receipt_id: str) -> None:
        async with self._lock:
            bucket = self._data.get("pending_receipts", {}).get(str(telegram_user_id))
            if not bucket or receipt_id not in bucket:
                return
            bucket.pop(receipt_id, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    async def set_active_receipt_edit(self, telegram_user_id: int, receipt_id: Optional[str]) -> None:
        async with self._lock:
            if receipt_id is None:
                self._data.get("active_receipt_edit", {}).pop(str(telegram_user_id), None)
            else:
                self._data.setdefault("active_receipt_edit", {})[str(telegram_user_id)] = receipt_id
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    async def get_active_receipt_edit(self, telegram_user_id: int) -> Optional[str]:
        async with self._lock:
            return self._data.get("active_receipt_edit", {}).get(str(telegram_user_id))
