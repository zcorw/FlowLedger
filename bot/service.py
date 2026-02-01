from __future__ import annotations

from typing import Any, Optional, Tuple, List
from uuid import uuid4

import httpx

from config import Config
from state_store import StateStore


class BotService:
    def __init__(self, config: Config):
        self.config = config
        self.state = StateStore(config.state_path)
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        self.client = httpx.AsyncClient(base_url=self.config.api_base_url.rstrip("/"), timeout=15)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    async def ensure_user(self, telegram_user_id: int) -> Tuple[Optional[int], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        cached = await self.state.get_user_id(telegram_user_id)
        if cached:
            return cached, None
        return None, "Account not linked yet. Use /start <username> <password>."

    async def get_cached_user(self, telegram_user_id: int) -> Tuple[Optional[int], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        cached = await self.state.get_user_id(telegram_user_id)
        if not cached:
            return None, "Account not linked yet. Use /start <username> <password>."
        return cached, None

    async def get_cached_token(self, telegram_user_id: int) -> Tuple[Optional[str], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        token = await self.state.get_token(telegram_user_id)
        if not token:
            return None, "Account not linked yet. Use /start <username> <password>."
        return token, None

    async def login_and_link(
        self, telegram_user_id: int, username: str, password: str
    ) -> Tuple[Optional[int], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        if not self.client:
            return None, "HTTP client is not ready."
        if not username or not password:
            return None, "Username and password are required."

        try:
            resp = await self.client.post(
                "/auth/login",
                json={"username": username, "password": password},
            )
        except Exception as exc:
            return None, f"Failed to login: {exc}"

        if resp.status_code >= 400:
            return None, f"Login failed: {resp.text}"

        data = resp.json()
        token = data.get("access_token")
        user = data.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            return None, "Login succeeded but user_id is missing."
        if not token:
            return None, "Login succeeded but access_token is missing."

        link_data, err = await self.link_user_with_token(token, telegram_user_id, link_token=None)
        if err:
            return None, err

        await self.state.set_user_id(telegram_user_id, link_data["id"])
        await self.state.set_token(telegram_user_id, token)
        return link_data["id"], None

    async def link_user_with_token(
        self, token: str, telegram_user_id: int, link_token: Optional[str]
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."

        payload: dict[str, Any] = {"telegram_user_id": telegram_user_id}
        if link_token:
            payload["link_token"] = link_token

        try:
            resp = await self.client.post(
                "/users/link-telegram",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": str(uuid4()),
                },
                json=payload,
            )
        except Exception as exc:
            return None, f"Failed to link Telegram user: {exc}"

        if resp.status_code == 409:
            return None, "This Telegram account is already bound to another user."
        if resp.status_code == 404:
            return None, "Link token is invalid."
        if resp.status_code >= 400:
            return None, f"Link failed: {resp.text}"

        data = resp.json()
        await self.state.set_user_id(telegram_user_id, data["id"])
        return data, None

    async def fetch_user(self, token: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        except Exception as exc:
            return None, f"Failed to fetch user: {exc}"
        if resp.status_code == 401:
            return None, "Session expired. Use /start <username> <password>."
        if resp.status_code >= 400:
            return None, f"Failed to fetch user: {resp.text}"
        return resp.json(), None

    async def fetch_preferences(self, token: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.patch(
                "/users/me/preferences", headers={"Authorization": f"Bearer {token}"}, json={}
            )
        except Exception as exc:
            return None, f"Failed to fetch preferences: {exc}"
        if resp.status_code >= 400:
            return None, f"Failed to fetch preferences: {resp.text}"
        return resp.json(), None

    async def update_preference(
        self, token: str, field: str, value: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        payload = {field: value}
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.patch(
                "/users/me/preferences", headers={"Authorization": f"Bearer {token}"}, json=payload
            )
        except Exception as exc:
            return None, f"Failed to update preference: {exc}"

        if resp.status_code == 422:
            detail = resp.json().get("detail")
            return None, f"Validation failed: {detail}"
        if resp.status_code >= 400:
            return None, f"Failed to update preference: {resp.text}"
        return resp.json(), None

    async def upload_receipt(
        self, token: str, filename: str, content_type: str, content: bytes
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.post(
                "/import/expense/receipt",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (filename, content, content_type)},
            )
        except Exception as exc:
            return None, f"Failed to upload receipt: {exc}"
        if resp.status_code >= 400:
            return None, f"Receipt upload failed: {resp.text}"
        return resp.json(), None

    async def fetch_receipt_task(
        self, token: str, task_id: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.get(
                f"/import/expense/receipt/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception as exc:
            return None, f"Failed to fetch receipt task: {exc}"
        if resp.status_code >= 400:
            return None, f"Failed to fetch receipt task: {resp.text}"
        return resp.json(), None

    async def list_categories(
        self, token: str
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.get(
                "/categories",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception as exc:
            return None, f"Failed to fetch categories: {exc}"
        if resp.status_code >= 400:
            return None, f"Failed to fetch categories: {resp.text}"
        data = resp.json()
        return data.get("data", []), None

    async def create_expense(
        self, token: str, payload: dict[str, Any]
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.post(
                "/expenses",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
        except Exception as exc:
            return None, f"Failed to create expense: {exc}"
        if resp.status_code >= 400:
            return None, f"Expense create failed: {resp.text}"
        return resp.json(), None
    async def list_institutions(
        self, token: str
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.get(
                "/institutions",
                headers={"Authorization": f"Bearer {token}"},
            )
        except Exception as exc:
            return None, f"Failed to fetch institutions: {exc}"
        if resp.status_code >= 400:
            return None, f"Failed to fetch institutions: {resp.text}"
        data = resp.json()
        return data.get("data", []), None