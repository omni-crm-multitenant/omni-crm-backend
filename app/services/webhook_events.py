from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import WebhookEvent


LEASE_SECONDS = 60
BACKOFF_SECONDS = (5, 30, 120, 600, 1800)


async def claim_webhook_event(session: AsyncSession, event_id: UUID, *, now: datetime | None = None) -> tuple[WebhookEvent, str] | None:
    now = now or datetime.now(UTC)
    event = await session.scalar(select(WebhookEvent).where(
        WebhookEvent.id == event_id,
        or_(WebhookEvent.status.in_(("received", "failed")), (WebhookEvent.status == "processing") & (WebhookEvent.lease_expires_at <= now)),
        WebhookEvent.next_attempt_at <= now,
    ).with_for_update())
    if event is None or event.status in {"dead_letter", "processed"}:
        return None
    token = secrets.token_hex(32)
    event.status = "processing"
    event.attempts += 1
    event.lease_token = token
    event.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    await session.flush()
    return event, token


async def complete_webhook_event(session: AsyncSession, event_id: UUID, lease_token: str) -> bool:
    event = await session.scalar(select(WebhookEvent).where(
        WebhookEvent.id == event_id, WebhookEvent.status == "processing", WebhookEvent.lease_token == lease_token,
    ).with_for_update())
    if event is None:
        return False
    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    event.lease_expires_at = None
    await session.flush()
    return True


async def fail_webhook_event(session: AsyncSession, event_id: UUID, lease_token: str, error_code: str) -> bool:
    event = await session.scalar(select(WebhookEvent).where(
        WebhookEvent.id == event_id, WebhookEvent.status == "processing", WebhookEvent.lease_token == lease_token,
    ).with_for_update())
    if event is None:
        return False
    event.error_code = error_code
    event.lease_expires_at = None
    if event.attempts >= len(BACKOFF_SECONDS):
        event.status = "dead_letter"
    else:
        event.status = "failed"
        event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=BACKOFF_SECONDS[event.attempts - 1])
    await session.flush()
    return True


async def redrive_webhook_event(session: AsyncSession, event_id: UUID) -> bool:
    event = await session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id).with_for_update())
    if event is None or event.status != "dead_letter":
        return False
    event.status = "received"
    event.attempts = 0
    event.error_code = None
    event.next_attempt_at = datetime.now(UTC)
    await session.flush()
    return True
