from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingUsageEvent, Subscription
from app.models.crm import Contact, Conversation
from app.models.identity import ChannelAsset


async def record_usage_event(session: AsyncSession, *, tenant_id: UUID, subscription_id: UUID, meter: str, event_key: str, quantity: int = 1) -> BillingUsageEvent:
    row = await session.scalar(select(BillingUsageEvent).where(
        BillingUsageEvent.tenant_id == tenant_id, BillingUsageEvent.subscription_id == subscription_id,
        BillingUsageEvent.meter == meter, BillingUsageEvent.event_key == event_key,
    ).with_for_update())
    if row is not None:
        return row
    row = BillingUsageEvent(tenant_id=tenant_id, subscription_id=subscription_id, meter=meter, event_key=event_key, quantity=quantity)
    session.add(row)
    await session.flush()
    return row


async def usage_meters(session: AsyncSession, *, tenant_id: UUID, at: date | None = None) -> dict[str, int]:
    at = at or datetime.now(UTC).date()
    subscription = await session.scalar(select(Subscription).where(
        Subscription.tenant_id == tenant_id, Subscription.status.in_(("trialing", "active", "past_due")),
        Subscription.payment_period_start <= at, Subscription.payment_period_end > at,
    ))
    if subscription is None:
        return {"contacts": 0, "connected_assets": 0, "conversations": 0}
    contacts = await session.scalar(select(func.count(Contact.id)).where(Contact.tenant_id == tenant_id, Contact.status != "deleted", Contact.deleted_at.is_(None)))
    assets = await session.scalar(select(func.count(ChannelAsset.id)).where(ChannelAsset.tenant_id == tenant_id, ChannelAsset.status == "connected", ChannelAsset.channel.in_(("whatsapp", "messenger", "instagram"))))
    conversations = await session.scalar(select(func.count(Conversation.id)).where(
        Conversation.tenant_id == tenant_id, Conversation.created_at >= datetime.combine(subscription.payment_period_start, datetime.min.time(), tzinfo=UTC),
        Conversation.created_at < datetime.combine(subscription.payment_period_end, datetime.min.time(), tzinfo=UTC),
    ))
    return {"contacts": int(contacts or 0), "connected_assets": int(assets or 0), "conversations": int(conversations or 0)}
