from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.channel_adapters import InstagramAdapter, MessengerAdapter, WhatsAppAdapter
from app.services.lead_ingestion import parse_lead_notification


_PERSONAL_KEYS = re.compile(r"(?:name|email|phone|from|to|recipient|sender|user_id|username|text)$", re.IGNORECASE)


def anonymize_meta_fixture(value: Any, *, field_name: str = "") -> Any:
    if isinstance(value, dict):
        return {key: anonymize_meta_fixture(item, field_name=key) for key, item in value.items()}
    if isinstance(value, list):
        return [anonymize_meta_fixture(item, field_name=field_name) for item in value]
    if isinstance(value, str) and _PERSONAL_KEYS.search(field_name):
        if "email" in field_name.lower():
            return "synthetic@example.test"
        if "phone" in field_name.lower() or field_name.lower() in {"from", "to"}:
            return "15550000000"
        return "Synthetic User"
    return value


def save_anonymized_fixture(payload: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(anonymize_meta_fixture(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_fixture(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "whatsapp_inbound":
        value = WhatsAppAdapter().parse_inbound(payload)
        return {"external_user_id": value.external_user_id, "provider_message_id": value.provider_message_id, "body_text": value.body_text, "direction": value.direction}
    if kind == "instagram_inbound":
        value = InstagramAdapter().parse_inbound(payload)
        return {"external_user_id": value.external_user_id, "provider_message_id": value.provider_message_id, "body_text": value.body_text, "direction": value.direction}
    if kind == "messenger_inbound":
        value = MessengerAdapter().parse_inbound(payload)
        return {"external_user_id": value.external_user_id, "provider_message_id": value.provider_message_id, "body_text": value.body_text, "direction": value.direction}
    if kind == "leadgen":
        lead = parse_lead_notification(payload)
        return {"leadgen_id": lead.leadgen_id, "page_id": lead.page_id, "ad_id": lead.ad_id, "form_id": lead.form_id}
    if kind == "whatsapp_status":
        status = (payload.get("statuses") or [{}])[0]
        return {"id": status.get("id"), "status": status.get("status"), "recipient_id": status.get("recipient_id")}
    raise ValueError(f"unsupported fixture kind: {kind}")
