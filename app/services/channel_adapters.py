from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.services.credentials import CredentialStore, get_credential_store
from app.services.egress import hardened_http_client


@dataclass(frozen=True)
class NormalizedMessage:
    external_user_id: str
    provider_message_id: str
    body_text: str | None
    occurred_at: datetime
    direction: str = "inbound"

    @property
    def text(self) -> str | None:
        return self.body_text


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str | None
    status: str
    raw: dict[str, Any] | None = None


class MessagingPolicyError(PermissionError):
    pass


def enforce_standard_messaging_window(*, sent_at: datetime, now: datetime | None = None, tag: str | None = None) -> None:
    reference = now or datetime.now(UTC)
    if reference - sent_at > __import__("datetime").timedelta(hours=24) and not tag:
        raise MessagingPolicyError("MESSAGING_WINDOW_EXPIRED")


class ChannelAdapter(Protocol):
    def parse_inbound(self, payload: dict[str, Any]) -> NormalizedMessage: ...
    async def send_text(self, asset: Any, to: str, text: str) -> SendResult: ...


class WhatsAppAdapter:
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self.credential_store = credential_store or get_credential_store()

    def parse_inbound(self, payload: dict[str, Any]) -> NormalizedMessage:
        message = payload.get("messages", [payload])[0]
        timestamp = int(message.get("timestamp", 0))
        return NormalizedMessage(
            external_user_id=str(message.get("from", "")),
            provider_message_id=str(message.get("id", "")),
            body_text=message.get("text", {}).get("body") if isinstance(message.get("text"), dict) else None,
            occurred_at=datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else datetime.now(UTC),
        )

    async def send_text(self, asset: Any, to: str, text: str, *, sent_at: datetime | None = None, tag: str | None = None) -> SendResult:
        if sent_at is not None:
            enforce_standard_messaging_window(sent_at=sent_at, tag=tag)
        token = await self.credential_store.get(asset.credential_ref)
        settings = get_settings()
        url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{asset.external_id}/messages"
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
        try:
            async with hardened_http_client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("WHATSAPP_SEND_FAILED") from exc
        messages = data.get("messages") if isinstance(data, dict) else None
        provider_id = messages[0].get("id") if isinstance(messages, list) and messages else None
        return SendResult(provider_message_id=provider_id, status="sent", raw=data)


class InstagramAdapter:
    def parse_inbound(self, payload: dict[str, Any]) -> NormalizedMessage:
        message = payload.get("message", payload)
        return NormalizedMessage(
            external_user_id=str((payload.get("sender") or {}).get("id", "")),
            provider_message_id=str(message.get("mid", "")),
            body_text=message.get("text"),
            occurred_at=datetime.fromtimestamp(int(payload["timestamp"]) / 1000, tz=UTC) if payload.get("timestamp") else datetime.now(UTC),
        )

    async def send_text(self, asset: Any, to: str, text: str, *, sent_at: datetime | None = None, tag: str | None = None) -> SendResult:
        if sent_at is not None:
            enforce_standard_messaging_window(sent_at=sent_at, tag=tag)
        token = await get_credential_store().get(asset.credential_ref)
        settings = get_settings()
        url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{asset.external_id}/messages"
        payload = {"recipient": {"id": to}, "message": {"text": text}}
        async with hardened_http_client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            response = await client.post(url, params={"access_token": token}, json=payload)
            response.raise_for_status()
            data = response.json()
        return SendResult(provider_message_id=(data.get("message_id") if isinstance(data, dict) else None), status="sent", raw=data)


class MessengerAdapter(InstagramAdapter):
    pass
