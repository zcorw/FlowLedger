from __future__ import annotations

from typing import Any, Optional, Tuple
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

        if not self.client:
            return None, "HTTP client is not ready."

        try:
            resp = await self.client.post("/users", headers={"Idempotency-Key": str(uuid4())})
            resp.raise_for_status()
        except Exception as exc:
            return None, f"Failed to register user: {exc}"

        data = resp.json()
        user_id = data["user"]["id"]
        link_data, err = await self.link_user(user_id, telegram_user_id, link_token=None)
        if err:
            return None, err

        await self.state.set_user_id(telegram_user_id, link_data["id"])
        return link_data["id"], None

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
        user = data.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            return None, "Login succeeded but user_id is missing."

        link_data, err = await self.link_user(user_id, telegram_user_id, link_token=None)
        if err:
            return None, err

        await self.state.set_user_id(telegram_user_id, link_data["id"])
        return link_data["id"], None

    async def link_user(
        self, user_id: int, telegram_user_id: int, link_token: Optional[str]
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."

        payload: dict[str, Any] = {"telegram_user_id": telegram_user_id}
        if link_token:
            payload["link_token"] = link_token

        try:
            resp = await self.client.post(
                "/users/link-telegram",
                headers={"X-User-Id": str(user_id), "Idempotency-Key": str(uuid4())},
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

    async def fetch_user(self, user_id: int) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.get("/users/me", headers={"X-User-Id": str(user_id)})
        except Exception as exc:
            return None, f"Failed to fetch user: {exc}"
        if resp.status_code == 401:
            return None, "User is not linked yet."
        if resp.status_code >= 400:
            return None, f"Failed to fetch user: {resp.text}"
        return resp.json(), None

    async def fetch_preferences(self, user_id: int) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.patch(
                "/users/me/preferences", headers={"X-User-Id": str(user_id)}, json={}
            )
        except Exception as exc:
            return None, f"Failed to fetch preferences: {exc}"
        if resp.status_code >= 400:
            return None, f"Failed to fetch preferences: {resp.text}"
        return resp.json(), None

    async def update_preference(
        self, user_id: int, field: str, value: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        payload = {field: value}
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await self.client.patch(
                "/users/me/preferences", headers={"X-User-Id": str(user_id)}, json=payload
            )
        except Exception as exc:
            return None, f"Failed to update preference: {exc}"

        if resp.status_code == 422:
            detail = resp.json().get("detail")
            return None, f"Validation failed: {detail}"
        if resp.status_code >= 400:
            return None, f"Failed to update preference: {resp.text}"
        return resp.json(), None
