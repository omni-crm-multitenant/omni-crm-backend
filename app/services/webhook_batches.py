from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


class InvalidWebhookSignature(ValueError):
    pass


class InvalidWebhookPayload(ValueError):
    pass


@dataclass(frozen=True)
class WebhookEnvelope:
    provider: str
    routing_external_id: str
    event_kind: str
    native_event_id: str
    payload: dict[str, Any]


def validate_meta_signature(raw_body: bytes, signature: str | None, app_secret: str) -> None:
    if not signature or not signature.startswith("sha256=") or not app_secret:
        raise InvalidWebhookSignature("invalid signature")
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise InvalidWebhookSignature("invalid signature")


def split_meta_batch(raw_body: bytes, *, signature: str | None, app_secret: str) -> list[WebhookEnvelope]:
    """Validate raw bytes first, then split Meta messaging/status events without side effects."""
    validate_meta_signature(raw_body, signature, app_secret)
    try:
        document = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidWebhookPayload("invalid JSON payload") from exc
    if not isinstance(document, dict) or not isinstance(document.get("entry"), list):
        raise InvalidWebhookPayload("entry must be a list")

    envelopes: list[WebhookEnvelope] = []
    for entry in document["entry"]:
        if not isinstance(entry, dict):
            raise InvalidWebhookPayload("entry must be an object")
        entry_id = str(entry.get("id") or "")
        for event in entry.get("messaging", []) or []:
            if not isinstance(event, dict):
                raise InvalidWebhookPayload("messaging event must be an object")
            recipient = event.get("recipient") or {}
            routing_id = str(recipient.get("id") or entry_id)
            message = event.get("message") or {}
            native_id = str(message.get("mid") or event.get("timestamp") or "")
            if not routing_id or not native_id:
                raise InvalidWebhookPayload("messaging event lacks routing or native id")
            envelopes.append(WebhookEnvelope("meta", routing_id, "message", native_id, event))
        for change in entry.get("changes", []) or []:
            if not isinstance(change, dict):
                raise InvalidWebhookPayload("change must be an object")
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            routing_id = str(metadata.get("phone_number_id") or entry_id)
            for message in value.get("messages", []) or []:
                native_id = str(message.get("id") or "")
                if routing_id and native_id:
                    envelopes.append(WebhookEnvelope("meta", routing_id, "message", native_id, message))
            for delivery in value.get("statuses", []) or []:
                native_id = str(delivery.get("id") or "")
                timestamp = str(delivery.get("timestamp") or "")
                if routing_id and native_id:
                    discriminator = f"{native_id}:{timestamp}:{delivery.get('status', '')}"
                    envelopes.append(WebhookEnvelope("meta", routing_id, "delivery_status", discriminator, delivery))
    return envelopes


validate_and_split_batch = split_meta_batch
