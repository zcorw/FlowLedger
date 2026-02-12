from __future__ import annotations

from typing import Any, Optional, Tuple, List, Callable, Awaitable
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

    def with_user(self, telegram_user_id: Optional[int]) -> "UserScopedBotService":
        return UserScopedBotService(self, telegram_user_id)

    async def ensure_user(self, telegram_user_id: int) -> Tuple[Optional[int], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        cached = await self.state.get_user_id(telegram_user_id)
        if cached:
            return cached, None
        return None, "Account not linked yet. Use /start &lt;username&gt; &lt;password&gt;."

    async def get_cached_user(self, telegram_user_id: int) -> Tuple[Optional[int], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        cached = await self.state.get_user_id(telegram_user_id)
        if not cached:
            return None, "Account not linked yet. Use /start &lt;username&gt; &lt;password&gt;."
        return cached, None

    async def get_cached_token(self, telegram_user_id: int) -> Tuple[Optional[str], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        token = await self.state.get_token(telegram_user_id)
        if token:
            return token, None
        login_token = await self.state.get_login_token(telegram_user_id)
        if login_token:
            refreshed, err = await self.login_with_bot_token(telegram_user_id)
            if refreshed:
                return refreshed, None
            return None, err or "Account not linked yet. Use /start &lt;username&gt; &lt;password&gt;."
        return None, "Account not linked yet. Use /start &lt;username&gt; &lt;password&gt;."

    async def _handle_unauthorized(self, telegram_user_id: Optional[int]) -> None:
        if telegram_user_id is None:
            return
        await self.state.clear_token(telegram_user_id)
        await self.state.clear_refresh_token(telegram_user_id)
        await self.state.clear_user_id(telegram_user_id)

    async def _reject_bot_login_token(
        self, telegram_user_id: int, message: str
    ) -> Tuple[Optional[str], Optional[str]]:
        await self.state.clear_login_token(telegram_user_id)
        return None, message

    async def _fallback_bot_login(
        self, telegram_user_id: Optional[int], *, message: str
    ) -> Tuple[Optional[str], Optional[str]]:
        login_token = await self.state.get_login_token(telegram_user_id)
        if login_token:
            token, err = await self.login_with_bot_token(telegram_user_id)
            if token:
                return token, None
            await self._handle_unauthorized(telegram_user_id)
            return None, err or message
        await self._handle_unauthorized(telegram_user_id)
        return None, message

    async def _retry_unauthorized(
        self,
        resp: httpx.Response,
        telegram_user_id: Optional[int],
        retry_request: Callable[[str], Awaitable[httpx.Response]],
        *,
        error_prefix: str,
    ) -> Tuple[httpx.Response, Optional[str]]:
        if resp.status_code != 401:
            return resp, None
        refreshed, refresh_err = await self._refresh_access_token(telegram_user_id)
        if not refreshed:
            return resp, refresh_err
        try:
            resp = await retry_request(refreshed)
        except Exception as exc:
            return resp, f"{error_prefix}: {exc}"
        if resp.status_code == 401:
            await self._handle_unauthorized(telegram_user_id)
            return resp, "Session expired. Use /start &lt;username&gt; &lt;password&gt;."
        return resp, None

    async def _request_with_retry(
        self,
        telegram_user_id: Optional[int],
        token: str,
        request_builder: Callable[[str], Awaitable[httpx.Response]],
        *,
        error_prefix: str,
        http_error_handler: Optional[Callable[[httpx.Response], Optional[str]]] = None,
    ) -> Tuple[Optional[httpx.Response], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        try:
            resp = await request_builder(token)
        except Exception as exc:
            return None, f"{error_prefix}: {exc}"
        resp, err = await self._retry_unauthorized(
            resp, telegram_user_id, request_builder, error_prefix=error_prefix
        )
        if err:
            return None, err
        if http_error_handler:
            custom_error = http_error_handler(resp)
            if custom_error:
                return None, custom_error
        if resp.status_code >= 400:
            return None, f"{error_prefix}: {resp.text}"
        return resp, None

    async def login_with_bot_token(
        self, telegram_user_id: Optional[int]
    ) -> Tuple[Optional[str], Optional[str]]:
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        if not self.client:
            return None, "HTTP client is not ready."
        login_token = await self.state.get_login_token(telegram_user_id)
        if not login_token:
            return None, "Bot login token not set. Use /start &lt;username&gt; &lt;password&gt;."
        if not self.config.internal_token:
            return None, "BOT_INTERNAL_TOKEN is not configured for the bot."

        try:
            resp = await self.client.post(
                "/auth/telegram-login",
                headers={"X-Internal-Token": self.config.internal_token},
                json={"telegram_user_id": telegram_user_id, "token": login_token},
            )
        except Exception as exc:
            return None, f"Failed to login with bot token: {exc}"

        if resp.status_code == 409:
            return await self._reject_bot_login_token(
                telegram_user_id,
                "Bot login token not set on the account. Use /start &lt;username&gt; &lt;password&gt;.",
            )
        if resp.status_code == 401:
            return await self._reject_bot_login_token(
                telegram_user_id,
                "Bot login token invalid. Use /start &lt;username&gt; &lt;password&gt;.",
            )
        if resp.status_code >= 400:
            return None, f"Bot login failed: {resp.text}"

        data = resp.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        user = data.get("user") or {}
        user_id = user.get("id")
        if not access_token or not refresh_token or not user_id:
            return None, "Bot login succeeded but response is incomplete."

        await self.state.set_token(telegram_user_id, access_token)
        await self.state.set_refresh_token(telegram_user_id, refresh_token)
        await self.state.set_user_id(telegram_user_id, user_id)
        return access_token, None

    async def _refresh_access_token(
        self, telegram_user_id: Optional[int]
    ) -> Tuple[Optional[str], Optional[str]]:
        if telegram_user_id is None:
            return None, "Session expired. Use /start &lt;username&gt; &lt;password&gt;."
        if not self.client:
            return None, "HTTP client is not ready."
        refresh_token = await self.state.get_refresh_token(telegram_user_id)
        if not refresh_token:
            return await self._fallback_bot_login(
                telegram_user_id,
                message="Session expired. Use /start &lt;username&gt; &lt;password&gt;.",
            )
        try:
            resp = await self.client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        except Exception as exc:
            return None, f"Failed to refresh session: {exc}"
        if resp.status_code >= 400:
            return await self._fallback_bot_login(
                telegram_user_id,
                message="Session expired. Use /start &lt;username&gt; &lt;password&gt;.",
            )
        data = resp.json()
        access_token = data.get("access_token")
        new_refresh = data.get("refresh_token")
        if not access_token or not new_refresh:
            await self._handle_unauthorized(telegram_user_id)
            return None, "Session expired. Use /start &lt;username&gt; &lt;password&gt;."
        await self.state.set_token(telegram_user_id, access_token)
        await self.state.set_refresh_token(telegram_user_id, new_refresh)
        return access_token, None

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
        refresh_token = data.get("refresh_token")
        user = data.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            return None, "Login succeeded but user_id is missing."
        if not token:
            return None, "Login succeeded but access_token is missing."
        if not refresh_token:
            return None, "Login succeeded but refresh_token is missing."

        await self.state.set_refresh_token(telegram_user_id, refresh_token)

        link_data, err = await self.link_user_with_token(
            token, telegram_user_id, link_token=None, requester_telegram_user_id=telegram_user_id
        )
        if err:
            return None, err

        await self.state.set_user_id(telegram_user_id, link_data["id"])
        await self.state.set_token(telegram_user_id, token)
        await self._ensure_bot_login_token(token, telegram_user_id)
        return link_data["id"], None

    async def _ensure_bot_login_token(
        self, token: str, telegram_user_id: Optional[int]
    ) -> Tuple[Optional[str], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."
        if telegram_user_id is None:
            return None, "Missing Telegram user information."
        if not self.config.internal_token:
            return None, "BOT_INTERNAL_TOKEN is not configured for the bot."
        existing = await self.state.get_login_token(telegram_user_id)
        if existing:
            return existing, None
        try:
            resp = await self.client.post(
                "/users/me/telegram-token/auto",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Internal-Token": self.config.internal_token,
                    "Idempotency-Key": str(uuid4()),
                },
            )
        except Exception as exc:
            return None, f"Failed to set bot login token: {exc}"

        if resp.status_code == 401:
            refreshed, refresh_err = await self._refresh_access_token(telegram_user_id)
            if not refreshed:
                return None, refresh_err
            try:
                resp = await self.client.post(
                    "/users/me/telegram-token/auto",
                    headers={
                        "Authorization": f"Bearer {refreshed}",
                        "X-Internal-Token": self.config.internal_token,
                        "Idempotency-Key": str(uuid4()),
                    },
                )
            except Exception as exc:
                return None, f"Failed to set bot login token: {exc}"
            if resp.status_code == 401:
                await self._handle_unauthorized(telegram_user_id)
                return None, "Session expired. Use /start &lt;username&gt; &lt;password&gt;."
        if resp.status_code == 409:
            return None, "Please link your Telegram account first."
        if resp.status_code >= 400:
            return None, f"Failed to set bot login token: {resp.text}"

        data = resp.json()
        login_token = data.get("token")
        if not login_token:
            return None, "Bot login token was not returned."
        await self.state.set_login_token(telegram_user_id, login_token)
        return login_token, None

    async def link_user_with_token(
        self,
        token: str,
        telegram_user_id: int,
        link_token: Optional[str],
        *,
        requester_telegram_user_id: Optional[int] = None,
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.client:
            return None, "HTTP client is not ready."

        payload: dict[str, Any] = {"telegram_user_id": telegram_user_id}
        if link_token:
            payload["link_token"] = link_token

        async def _link_request(bearer: str) -> httpx.Response:
            return await self.client.post(
                "/users/link-telegram",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Idempotency-Key": str(uuid4()),
                },
                json=payload,
            )

        resp, err = await self._request_with_retry(
            requester_telegram_user_id,
            token,
            _link_request,
            error_prefix="Failed to link Telegram user",
            http_error_handler=lambda resp: (
                "This Telegram account is already bound to another user."
                if resp.status_code == 409
                else "Link token is invalid."
                if resp.status_code == 404
                else f"Link failed: {resp.text}"
                if resp.status_code >= 400
                else None
            ),
        )
        if err:
            return None, err

        data = resp.json()
        await self.state.set_user_id(telegram_user_id, data["id"])
        return data, None

    async def fetch_user(
        self, token: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                "/users/me", headers={"Authorization": f"Bearer {bearer}"}
            ),
            error_prefix="Failed to fetch user",
        )
        if err:
            return None, err
        return resp.json(), None

    async def fetch_preferences(
        self, token: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.patch(
                "/users/me/preferences", headers={"Authorization": f"Bearer {bearer}"}, json={}
            ),
            error_prefix="Failed to fetch preferences",
        )
        if err:
            return None, err
        return resp.json(), None

    async def update_preference(
        self, token: str, field: str, value: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        payload = {field: value}
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.patch(
                "/users/me/preferences", headers={"Authorization": f"Bearer {bearer}"}, json=payload
            ),
            error_prefix="Failed to update preference",
            http_error_handler=lambda resp: (
                f"Validation failed: {resp.json().get('detail')}"
                if resp.status_code == 422
                else None
            ),
        )
        if err:
            return None, err
        return resp.json(), None

    async def upload_receipt(
        self,
        token: str,
        filename: str,
        content_type: str,
        content: bytes,
        telegram_user_id: Optional[int] = None,
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.post(
                "/import/expense/receipt",
                headers={"Authorization": f"Bearer {bearer}"},
                files={"file": (filename, content, content_type)},
            ),
            error_prefix="Failed to upload receipt",
            http_error_handler=lambda resp: (
                f"Receipt upload failed: {resp.text}" if resp.status_code >= 400 else None
            ),
        )
        if err:
            return None, err
        return resp.json(), None

    async def upload_receipt_text(
        self,
        token: str,
        text: str,
        telegram_user_id: Optional[int] = None,
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.post(
                "/import/expense/receipt-text",
                headers={"Authorization": f"Bearer {bearer}"},
                json={"text": text},
            ),
            error_prefix="Failed to upload receipt text",
            http_error_handler=lambda resp: (
                f"Receipt text upload failed: {resp.text}" if resp.status_code >= 400 else None
            ),
        )
        if err:
            return None, err
        return resp.json(), None

    async def fetch_receipt_task(
        self, token: str, task_id: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                f"/import/expense/receipt/tasks/{task_id}",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch receipt task",
        )
        if err:
            return None, err
        return resp.json(), None

    async def fetch_receipt_text_task(
        self, token: str, task_id: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                f"/import/expense/receipt-text/tasks/{task_id}",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch receipt text task",
        )
        if err:
            return None, err
        return resp.json(), None

    async def list_categories(
        self, token: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                "/categories",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch categories",
        )
        if err:
            return None, err
        data = resp.json()
        return data.get("data", []), None

    async def create_expense(
        self, token: str, payload: dict[str, Any], telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.post(
                "/expenses",
                headers={"Authorization": f"Bearer {bearer}"},
                json=payload,
            ),
            error_prefix="Failed to create expense",
            http_error_handler=lambda resp: (
                f"Expense create failed: {resp.text}" if resp.status_code >= 400 else None
            ),
        )
        if err:
            return None, err
        return resp.json(), None

    async def list_institutions(
        self, token: str, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                "/institutions",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch institutions",
        )
        if err:
            return None, err
        data = resp.json()
        return data.get("data", []), None
    
    async def most_recent_categories(
        self, token: str, limit: int = 4, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                f"/categories/most-used?limit={limit}",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch categories-most-used",
        )
        if err:
            return None, err
        data = resp.json()
        return data.get("data", []), None
    
    async def most_recent_institutions(
        self, token: str, limit: int = 4, telegram_user_id: Optional[int] = None
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        resp, err = await self._request_with_retry(
            telegram_user_id,
            token,
            lambda bearer: self.client.get(
                f"/institutions/most-used?limit={limit}",
                headers={"Authorization": f"Bearer {bearer}"},
            ),
            error_prefix="Failed to fetch institutions-most-used",
        )
        if err:
            return None, err
        data = resp.json()
        return data.get("data", []), None


class UserScopedBotService:
    def __init__(self, base: BotService, telegram_user_id: Optional[int]):
        self._base = base
        self._telegram_user_id = telegram_user_id

    @property
    def state(self) -> StateStore:
        return self._base.state

    @property
    def config(self) -> Config:
        return self._base.config

    @property
    def client(self) -> Optional[httpx.AsyncClient]:
        return self._base.client

    async def get_cached_token(self) -> Tuple[Optional[str], Optional[str]]:
        return await self._base.get_cached_token(self._telegram_user_id)

    async def get_cached_user(self) -> Tuple[Optional[int], Optional[str]]:
        return await self._base.get_cached_user(self._telegram_user_id)

    async def ensure_user(self) -> Tuple[Optional[int], Optional[str]]:
        return await self._base.ensure_user(self._telegram_user_id)

    async def link_user_with_token(
        self, token: str, telegram_user_id: int, link_token: Optional[str]
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.link_user_with_token(
            token,
            telegram_user_id,
            link_token,
            requester_telegram_user_id=self._telegram_user_id,
        )

    async def fetch_user(self, token: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.fetch_user(token, self._telegram_user_id)

    async def fetch_preferences(self, token: str) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.fetch_preferences(token, self._telegram_user_id)

    async def update_preference(
        self, token: str, field: str, value: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.update_preference(token, field, value, self._telegram_user_id)

    async def upload_receipt(
        self, token: str, filename: str, content_type: str, content: bytes
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.upload_receipt(
            token, filename, content_type, content, self._telegram_user_id
        )

    async def upload_receipt_text(
        self, token: str, text: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.upload_receipt_text(token, text, self._telegram_user_id)

    async def fetch_receipt_task(
        self, token: str, task_id: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.fetch_receipt_task(token, task_id, self._telegram_user_id)

    async def fetch_receipt_text_task(
        self, token: str, task_id: str
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.fetch_receipt_text_task(
            token, task_id, self._telegram_user_id
        )

    async def list_categories(
        self, token: str
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        return await self._base.list_categories(token, self._telegram_user_id)

    async def create_expense(
        self, token: str, payload: dict[str, Any]
    ) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
        return await self._base.create_expense(token, payload, self._telegram_user_id)

    async def list_institutions(
        self, token: str
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        return await self._base.list_institutions(token, self._telegram_user_id)

    async def most_recent_categories(
        self, token: str, limit: int = 4
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        return await self._base.most_recent_categories(token, limit, self._telegram_user_id)
    
    async def most_recent_institutions(
        self, token: str, limit: int = 4
    ) -> Tuple[Optional[List[dict[str, Any]]], Optional[str]]:
        return await self._base.most_recent_institutions(token, limit, self._telegram_user_id)