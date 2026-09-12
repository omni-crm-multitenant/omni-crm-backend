from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiRun
from app.models.attribution import Attribution
from app.models.crm import Contact, Conversation, Message
from app.models.kpi import KpiEvent


async def open_response_window(session: AsyncSession, conversation: Conversation, received_at: datetime) -> UUID:
    if conversation.response_window_id is None:
        conversation.response_window_id = uuid4()
        conversation.response_window_started_at = received_at
        await session.flush()
    return conversation.response_window_id


async def close_response_window(
    session: AsyncSession,
    *,
    message: Message,
    responded_at: datetime | None = None,
) -> KpiEvent | None:
    if message.direction != "outbound" or message.status not in {"sent", "delivered", "read"}:
        return None
    if message.author_type == "user":
        responder_type = "agent"
    elif message.author_type in {"ai", "automation"}:
        responder_type = message.author_type
    else:
        return None
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == message.conversation_id,
        Conversation.tenant_id == message.tenant_id,
    ).with_for_update())
    if conversation is None or conversation.response_window_id is None or conversation.response_window_started_at is None:
        return None
    window_id = conversation.response_window_id
    received_at = conversation.response_window_started_at
    responded_at = responded_at or datetime.now(UTC)
    campaign_id = await session.scalar(select(Attribution.campaign_id).join(
        Contact, Contact.id == Attribution.contact_id,
    ).where(
        Attribution.tenant_id == message.tenant_id,
        Attribution.contact_id == conversation.contact_id,
        Attribution.campaign_id.is_not(None),
    ).order_by(Attribution.created_at.desc()).limit(1))
    ai_model = await session.scalar(select(AiRun.model).where(
        AiRun.tenant_id == message.tenant_id,
        AiRun.conversation_id == conversation.id,
    ).order_by(AiRun.created_at.desc()).limit(1))
    event = KpiEvent(
        tenant_id=message.tenant_id, conversation_id=conversation.id,
        response_window_id=window_id, channel=conversation.channel,
        campaign_id=campaign_id, responder_type=responder_type,
        responder_user_id=message.author_user_id if responder_type == "agent" else None,
        ai_model=ai_model if responder_type == "ai" else None,
        received_at=received_at, responded_at=responded_at,
        elapsed_ms=max(0, int((responded_at - received_at).total_seconds() * 1000)),
        resolved_by_ai=responder_type == "ai" and conversation.ai_mode == "active",
    )
    session.add(event)
    conversation.response_window_id = None
    conversation.response_window_started_at = None
    await session.flush()
    return event


def percentile(values: list[int], percentile_value: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percentile_value
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


async def first_response_metrics(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    channel: str | None = None,
    campaign_id: UUID | None = None,
    responder_type: str | None = None,
    responder_user_id: UUID | None = None,
    ai_model: str | None = None,
) -> dict[str, Any]:
    query = select(KpiEvent).where(KpiEvent.tenant_id == tenant_id)
    if start:
        query = query.where(KpiEvent.received_at >= start)
    if end:
        query = query.where(KpiEvent.received_at < end)
    for field, value in ((KpiEvent.channel, channel), (KpiEvent.campaign_id, campaign_id), (KpiEvent.responder_type, responder_type), (KpiEvent.responder_user_id, responder_user_id), (KpiEvent.ai_model, ai_model)):
        if value is not None:
            query = query.where(field == value)
    rows = list((await session.scalars(query)).all())
    elapsed = [row.elapsed_ms for row in rows]
    return {
        "count": len(elapsed),
        "median_ms": percentile(elapsed, 0.5),
        "p90_ms": percentile(elapsed, 0.9),
        "percent_answered_within_60s": (sum(value <= 60_000 for value in elapsed) / len(elapsed) * 100) if elapsed else 0.0,
        "percent_resolved_by_ai": (sum(row.resolved_by_ai for row in rows) / len(rows) * 100) if rows else 0.0,
    }
