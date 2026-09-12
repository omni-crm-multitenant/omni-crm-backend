from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingEvent
from app.services.billing_provider import BillingProvider


async def process_billing_event(
    session: AsyncSession,
    *,
    provider: BillingProvider,
    tenant_id: UUID | None,
    headers: dict[str, str],
    body: bytes,
) -> BillingEvent:
    normalized = await provider.verify_and_normalize_event(headers, body)
    existing = await session.scalar(select(BillingEvent).where(
        BillingEvent.provider == "fake", BillingEvent.provider_event_id == normalized["provider_event_id"],
    ).with_for_update())
    if existing is not None:
        return existing
    event = BillingEvent(
        tenant_id=tenant_id, provider="fake", provider_event_id=str(normalized["provider_event_id"]),
        event_type=str(normalized["event_type"]), payload=normalized.get("payload", {}),
    )
    session.add(event)
    await session.flush()
    return event
