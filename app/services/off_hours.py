from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import ContactIdentity, Conversation, Message
from app.models.identity import Tenant
from app.models.operations import TenantSettings, WebhookEvent
from app.repositories.messages import create_message
from app.services.business_hours import is_within_business_hours
from app.services.message_authors import MessageAuthor
from app.services.send_intent import send_outbound_message
from app.services.kpi import open_response_window
from app.services.conversation_timers import cancel_unanswered_timers, schedule_unanswered_timers


def next_business_opening(at: datetime, timezone: str, business_hours: dict[str, Any]) -> datetime | None:
    local = (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(ZoneInfo(timezone))
    for offset in range(8):
        day = local + timedelta(days=offset)
        windows = business_hours.get(day.strftime("%A").lower(), []) or []
        for window in sorted(windows, key=lambda value: value.get("open", "")):
            try:
                opening = time.fromisoformat(window["open"])
            except (KeyError, TypeError, ValueError):
                continue
            candidate = datetime.combine(day.date(), opening, tzinfo=local.tzinfo)
            if candidate > local:
                return candidate
    return None


async def route_inbound_message(session: AsyncSession, *, event: WebhookEvent, contact_id: UUID, at: datetime) -> Conversation | None:
    """Persist inbound conversation effects, then gate AI/human routing on hours."""
    if event.channel_asset_id is None:
        return None
    from app.models.identity import ChannelAsset
    asset = await session.scalar(select(ChannelAsset).where(
        ChannelAsset.id == event.channel_asset_id, ChannelAsset.tenant_id == event.tenant_id,
    ))
    if asset is None:
        return None
    conversation = await session.scalar(select(Conversation).where(
        Conversation.tenant_id == event.tenant_id,
        Conversation.contact_id == contact_id,
        Conversation.channel_asset_id == asset.id,
        Conversation.channel == asset.channel,
        Conversation.status.in_(("open", "pending")),
    ).order_by(Conversation.last_message_at.desc().nullslast()).limit(1).with_for_update())
    if conversation is None:
        conversation = Conversation(
            tenant_id=event.tenant_id, contact_id=contact_id,
            channel_asset_id=asset.id, channel=asset.channel, status="open",
        )
        session.add(conversation)
        await session.flush()
    payload = event.payload or {}
    raw = payload.get("messages", [payload])
    raw = raw[0] if isinstance(raw, list) and raw else payload
    provider_id = str(raw.get("id") or event.native_event_id)
    duplicate = await session.scalar(select(Message).where(
        Message.tenant_id == event.tenant_id,
        Message.channel_asset_id == asset.id,
        Message.provider_message_id == provider_id,
    ))
    if duplicate is not None:
        return conversation
    identity = await session.scalar(select(ContactIdentity).where(
        ContactIdentity.tenant_id == event.tenant_id,
        ContactIdentity.contact_id == contact_id,
        ContactIdentity.channel_asset_id == asset.id,
    ).order_by(ContactIdentity.last_seen_at.desc().nullslast()).limit(1))
    if identity is None:
        return conversation
    text = raw.get("text", {}).get("body") if isinstance(raw.get("text"), dict) else raw.get("text")
    message = await create_message(
        session, tenant_id=event.tenant_id, conversation_id=conversation.id,
        channel_asset_id=asset.id, channel=asset.channel, direction="inbound",
        status="delivered", author=MessageAuthor.contact(identity.id),
        body_text=text, provider_message_id=provider_id, occurred_at=at,
    )
    await open_response_window(session, conversation, at)
    await cancel_unanswered_timers(session, tenant_id=conversation.tenant_id, conversation_id=conversation.id, trigger_type="customer_unanswered")
    await schedule_unanswered_timers(session, conversation=conversation, direction="inbound", message=message, now=at)
    conversation.last_message_at = at
    if await is_within_business_hours(session, event.tenant_id, at):
        return conversation
    settings = await session.get(TenantSettings, event.tenant_id)
    tenant = await session.get(Tenant, event.tenant_id)
    policy = (settings.off_hours_policy if settings else {}) or {}
    conversation.status = "pending"
    if policy.get("mode") == "auto_reply" and policy.get("message"):
        await send_outbound_message(
            session, tenant_id=event.tenant_id, conversation_id=conversation.id,
            body_text=str(policy["message"]), author=MessageAuthor.system(event.id),
            purpose="service", consent_required=False,
        )
    from app.models.tasks import Task
    due_at = next_business_opening(at, tenant.timezone if tenant else "America/Bogota", (settings.business_hours if settings else {}) or {})
    existing_task = await session.scalar(select(Task).where(
        Task.tenant_id == event.tenant_id, Task.conversation_id == conversation.id,
        Task.source == "system", Task.status == "open",
    ))
    if existing_task is None:
        session.add(Task(
            tenant_id=event.tenant_id, title="Atender conversación fuera de horario",
            description="Conversación en cola para el siguiente turno.", source="system",
            due_at=due_at, contact_id=contact_id, conversation_id=conversation.id,
        ))
    return conversation
