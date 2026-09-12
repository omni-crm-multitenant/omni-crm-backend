from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import WebhookEvent
from app.models.identity import ChannelAsset
from app.services.contacts import ContactResolution, find_or_create_contact_with_decision
from sqlalchemy import select
from app.services.webhook_events import complete_webhook_event
from app.services.off_hours import route_inbound_message


async def commit_webhook_effects(
    session: AsyncSession,
    *,
    event_id: UUID,
    lease_token: str,
    effect: Callable[[AsyncSession, WebhookEvent], Awaitable[Any]],
) -> bool:
    event = await session.get(WebhookEvent, event_id)
    if event is None or event.status != "processing" or event.lease_token != lease_token:
        return False
    await effect(session, event)
    return await complete_webhook_event(session, event_id, lease_token)


async def process_inbound_contact(session: AsyncSession, event: WebhookEvent) -> ContactResolution | None:
    if event.channel_asset_id is None or event.event_kind != "message":
        return None
    asset = await session.scalar(select(ChannelAsset).where(
        ChannelAsset.id == event.channel_asset_id, ChannelAsset.tenant_id == event.tenant_id
    ))
    if asset is None:
        return None
    payload = event.payload or {}
    message = payload.get("messages", [payload])[0] if isinstance(payload.get("messages", [payload]), list) else payload
    sender = payload.get("sender") or {}
    external_user_id = str(message.get("from") or sender.get("id") or "")
    if not external_user_id:
        return None
    profile = payload.get("contacts", [{}])[0] if isinstance(payload.get("contacts"), list) else {}
    profile_data = profile.get("profile") or {} if isinstance(profile, dict) else {}
    name = profile_data.get("name") or payload.get("name")
    phone = external_user_id if asset.channel == "whatsapp" else None
    resolution = await find_or_create_contact_with_decision(
        session,
        tenant_id=event.tenant_id,
        channel=asset.channel,
        channel_asset_id=asset.id,
        external_user_id=external_user_id,
        phone=phone,
        name=name,
    )
    occurred_at = event.received_at
    await route_inbound_message(session, event=event, contact_id=resolution.contact.id, at=occurred_at)
    return resolution
