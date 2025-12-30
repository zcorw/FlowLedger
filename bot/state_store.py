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
        self._data: dict[str, Any] = {"telegram_to_user": {}}
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
