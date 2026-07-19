"""HTTP client for WAHA (WhatsApp HTTP API)."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class WahaError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class WahaClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session_name: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.WAHA_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.WAHA_API_KEY
        self.session_name = session_name or settings.WAHA_SESSION_NAME

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Accept": accept,
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        timeout: float = 30.0,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(accept=accept),
                json=json,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise WahaError(f"WAHA request failed: {exc}") from exc
        return response

    def get_session(self, name: str | None = None) -> dict[str, Any] | None:
        session = name or self.session_name
        response = self._request("GET", f"/api/sessions/{session}")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise WahaError(
                f"Failed to get session: {response.text}",
                status_code=response.status_code,
            )
        return response.json()

    def create_session(self, name: str | None = None, *, start: bool = True) -> dict[str, Any]:
        session = name or self.session_name
        response = self._request(
            "POST",
            "/api/sessions",
            json={"name": session, "start": start},
        )
        if response.status_code >= 400:
            if response.status_code in {409, 422}:
                return self.start_session(session)
            raise WahaError(
                f"Failed to create session: {response.text}",
                status_code=response.status_code,
            )
        return response.json()

    def start_session(self, name: str | None = None) -> dict[str, Any]:
        session = name or self.session_name
        response = self._request("POST", f"/api/sessions/{session}/start")
        if response.status_code >= 400:
            raise WahaError(
                f"Failed to start session: {response.text}",
                status_code=response.status_code,
            )
        return response.json() if response.content else {"name": session}

    def ensure_session(self, name: str | None = None) -> dict[str, Any]:
        session = name or self.session_name
        existing = self.get_session(session)
        if existing is None:
            return self.create_session(session, start=True)
        status = str(existing.get("status") or "").upper()
        if status in {"STOPPED", "FAILED"}:
            return self.start_session(session)
        return existing

    def get_qr_base64(self, name: str | None = None) -> str | None:
        session = name or self.session_name
        response = self._request(
            "GET",
            f"/api/{session}/auth/qr",
            accept="application/json",
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise WahaError(
                f"Failed to get QR: {response.text}",
                status_code=response.status_code,
            )
        data = response.json()
        if isinstance(data, dict):
            if data.get("data"):
                return str(data["data"])
            if data.get("qrCode"):
                return str(data["qrCode"])
        return None

    def send_text(self, chat_id: str, text: str, *, session: str | None = None) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/sendText",
            json={
                "session": session or self.session_name,
                "chatId": chat_id,
                "text": text,
            },
        )
        if response.status_code >= 400:
            raise WahaError(
                f"Failed to send text to {chat_id}: {response.status_code} {response.text}",
                status_code=response.status_code,
            )
        return response.json() if response.content else {}

    def send_seen(
        self,
        chat_id: str,
        *,
        message_ids: list[str] | None = None,
        session: str | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "session": session or self.session_name,
            "chatId": chat_id,
        }
        if message_ids:
            body["messageIds"] = message_ids
        response = self._request("POST", "/api/sendSeen", json=body)
        if response.status_code >= 400:
            return

    def get_phone_by_lid(self, lid: str, *, session: str | None = None) -> str | None:
        """Resolve @lid → phone chat id (@c.us) via WAHA lids API."""
        value = normalize_chat_id(lid)
        if not value.endswith("@lid"):
            return None
        # Path may need the full lid or local part depending on WAHA version.
        local = value.split("@", 1)[0]
        for candidate in (value, local):
            encoded = candidate.replace("@", "%40")
            response = self._request(
                "GET",
                f"/api/{session or self.session_name}/lids/{encoded}",
            )
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                continue
            data = response.json()
            if isinstance(data, dict):
                pn = data.get("pn") or data.get("phoneNumber") or data.get("phone")
                if pn:
                    return normalize_chat_id(str(pn))
            if isinstance(data, str) and data.strip():
                return normalize_chat_id(data.strip())
        return None


def extract_outbound_id(payload: dict[str, Any] | None) -> str | None:
    """Best-effort WAHA sendText message id for outbound tracking."""
    if not isinstance(payload, dict):
        return None
    for key in ("id", "messageId", "key"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("id") or value.get("_serialized")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return extract_outbound_id(data)
    return None


def normalize_chat_id(chat_id: str) -> str:
    """Return trimmed WAHA chat id, converting @s.whatsapp.net → @c.us when needed."""
    value = (chat_id or "").strip()
    if value.endswith("@s.whatsapp.net"):
        local = value.split("@", 1)[0]
        return f"{local}@c.us"
    return value


def normalize_phone(chat_id: str) -> str:
    """Digits-only local part for phone-based chats. Empty for non-phone ids."""
    value = normalize_chat_id(chat_id)
    if not value:
        return ""
    if "@" in value:
        local, _, domain = value.partition("@")
        if domain.lower() not in {"c.us", "s.whatsapp.net"}:
            return ""
        value = local
    return "".join(ch for ch in value if ch.isdigit())


def to_chat_id(phone: str) -> str:
    """Build @c.us chat id from a phone number (not for @lid ids)."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"{digits}@c.us"


def is_group_or_broadcast(chat_id: str) -> bool:
    lowered = (chat_id or "").lower()
    return (
        lowered.endswith("@g.us")
        or lowered.endswith("@newsletter")
        or lowered.endswith("@broadcast")
    )


def is_user_chat(chat_id: str) -> bool:
    """True for direct chats (@c.us / @lid), false for groups/broadcasts/empty."""
    value = normalize_chat_id(chat_id)
    if not value or "@" not in value:
        return False
    if is_group_or_broadcast(value):
        return False
    domain = value.rsplit("@", 1)[-1].lower()
    return domain in {"c.us", "lid", "s.whatsapp.net"}
