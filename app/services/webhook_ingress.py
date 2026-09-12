from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import ChannelAsset
from app.models.operations import WebhookEvent
from app.services.webhook_batches import WebhookEnvelope


async def persist_webhook_envelopes(
    session: AsyncSession,
    envelopes: Iterable[WebhookEnvelope],
    *,
    meta_app_id: str,
) -> list[WebhookEvent]:
    persisted: list[WebhookEvent] = []
    for envelope in envelopes:
        event_key = "|".join(
            (envelope.provider, envelope.routing_external_id, envelope.event_kind, envelope.native_event_id)
        )
        existing = await session.scalar(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
        if existing is not None:
            persisted.append(existing)
            continue
        asset = await session.scalar(
            select(ChannelAsset).where(
                ChannelAsset.meta_app_id == meta_app_id,
                ChannelAsset.external_id == envelope.routing_external_id,
                ChannelAsset.status == "connected",
            )
        )
        tenant_id: UUID | None = asset.tenant_id if asset else None
        asset_id: UUID | None = asset.id if asset else None
        event = WebhookEvent(
            provider=envelope.provider,
            routing_external_id=envelope.routing_external_id,
            event_kind=envelope.event_kind,
            native_event_id=envelope.native_event_id,
            event_key=event_key,
            tenant_id=tenant_id,
            routing_asset_id=asset_id,
            channel_asset_id=asset_id,
            status="received" if asset else "quarantined",
            payload=envelope.payload,
        )
        session.add(event)
        persisted.append(event)
    await session.flush()
    return persisted
