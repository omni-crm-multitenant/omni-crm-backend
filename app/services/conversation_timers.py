from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_timers import ConversationTimer
from app.models.automation import AutomationRule
from app.models.crm import Conversation, Message
from app.services.domain_events import DomainEvent, publish_domain_event


async def schedule_timer(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    rule_id: UUID,
    rule_version: int,
    trigger_type: str,
    activity_version: int,
    deadline: datetime,
    trigger_message_id: UUID | None = None,
) -> ConversationTimer:
    timer = await session.scalar(select(ConversationTimer).where(
        ConversationTimer.tenant_id == tenant_id, ConversationTimer.conversation_id == conversation_id,
        ConversationTimer.rule_id == rule_id, ConversationTimer.rule_version == rule_version,
        ConversationTimer.activity_version == activity_version,
    ).with_for_update())
    if timer is None:
        timer = ConversationTimer(
            tenant_id=tenant_id, conversation_id=conversation_id, rule_id=rule_id,
            rule_version=rule_version, trigger_type=trigger_type,
            activity_version=activity_version, deadline=deadline,
            trigger_message_id=trigger_message_id,
        )
        session.add(timer)
        await session.flush()
    return timer


async def fire_due_timers(
    session: AsyncSession,
    *,
    enqueue: Callable[[ConversationTimer], Any | Awaitable[Any]] | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    now = now or datetime.now(UTC)
    timers = list((await session.scalars(select(ConversationTimer).where(
        ConversationTimer.status == "pending", ConversationTimer.deadline <= now,
    ).order_by(ConversationTimer.deadline, ConversationTimer.id).limit(limit).with_for_update(skip_locked=True))).all())
    fired = 0
    for timer in timers:
        rule = await session.get(AutomationRule, timer.rule_id)
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == timer.conversation_id,
            Conversation.tenant_id == timer.tenant_id,
        ).with_for_update())
        if rule is None or not rule.enabled or rule.version != timer.rule_version or conversation is None or conversation.status == "closed":
            timer.status = "cancelled"
            continue
        await publish_domain_event(session, DomainEvent(
            tenant_id=timer.tenant_id, type=timer.trigger_type,
            resource_id=timer.conversation_id,
            payload={"conversation_id": str(timer.conversation_id), "timer_id": str(timer.id), "trigger_type": timer.trigger_type},
        ))
        if enqueue is not None:
            result = enqueue(timer)
            if hasattr(result, "__await__"):
                await result
        timer.status = "fired"
        fired += 1
    await session.flush()
    return fired


async def cancel_unanswered_timers(session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, trigger_type: str) -> int:
    rows = list((await session.scalars(select(ConversationTimer).where(
        ConversationTimer.tenant_id == tenant_id, ConversationTimer.conversation_id == conversation_id,
        ConversationTimer.trigger_type == trigger_type, ConversationTimer.status == "pending",
    ).with_for_update())).all())
    for row in rows:
        row.status = "cancelled"
    await session.flush()
    return len(rows)


async def schedule_unanswered_timers(
    session: AsyncSession,
    *,
    conversation: Conversation,
    direction: str,
    message: Message,
    accepted: bool = True,
    now: datetime | None = None,
) -> int:
    if not accepted or message.author_type == "system":
        return 0
    now = now or datetime.now(UTC)
    trigger_type = "team_unanswered" if direction == "inbound" else "customer_unanswered"
    if direction == "outbound" and message.author_type not in {"user", "ai", "automation"}:
        return 0
    rules = list((await session.scalars(select(AutomationRule).where(
        AutomationRule.tenant_id == conversation.tenant_id,
        AutomationRule.enabled.is_(True), AutomationRule.trigger_type == trigger_type,
    ))).all())
    created = 0
    for rule in rules:
        pending = await session.scalar(select(ConversationTimer).where(
            ConversationTimer.tenant_id == conversation.tenant_id,
            ConversationTimer.conversation_id == conversation.id,
            ConversationTimer.rule_id == rule.id,
            ConversationTimer.trigger_type == trigger_type,
            ConversationTimer.status == "pending",
        ).with_for_update())
        if pending is not None:
            continue
        latest = await session.scalar(select(ConversationTimer.activity_version).where(
            ConversationTimer.tenant_id == conversation.tenant_id,
            ConversationTimer.conversation_id == conversation.id,
            ConversationTimer.rule_id == rule.id,
        ).order_by(ConversationTimer.activity_version.desc()).limit(1))
        activity_version = (latest or 0) + 1
        await schedule_timer(
            session, tenant_id=conversation.tenant_id, conversation_id=conversation.id,
            rule_id=rule.id, rule_version=rule.version, trigger_type=trigger_type,
            activity_version=activity_version, deadline=now + __import__("datetime").timedelta(seconds=rule.duration_seconds or 0),
            trigger_message_id=message.id,
        )
        created += 1
    return created
