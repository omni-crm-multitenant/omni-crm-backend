from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Message
from app.models.message_attempts import MessageSendAttempt


async def start_message_attempt(session: AsyncSession, *, tenant_id: UUID, message_id: UUID) -> MessageSendAttempt:
    current = await session.scalar(select(func.max(MessageSendAttempt.attempt_number)).where(
        MessageSendAttempt.tenant_id == tenant_id, MessageSendAttempt.message_id == message_id,
    ))
    attempt = MessageSendAttempt(
        tenant_id=tenant_id, message_id=message_id,
        attempt_number=(current or 0) + 1, status="dispatching",
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def finish_message_attempt(
    session: AsyncSession,
    attempt: MessageSendAttempt,
    *,
    status: str,
    provider_message_id: str | None = None,
    error_code: str | None = None,
) -> MessageSendAttempt:
    if status not in {"accepted", "rejected", "unknown"}:
        raise ValueError("invalid attempt status")
    attempt.status = status
    attempt.provider_message_id = provider_message_id
    attempt.error_code = error_code
    attempt.finished_at = datetime.now(UTC)
    await session.flush()
    return attempt


async def list_message_attempts(session: AsyncSession, *, tenant_id: UUID, message_id: UUID) -> list[MessageSendAttempt]:
    return list((await session.scalars(select(MessageSendAttempt).where(
        MessageSendAttempt.tenant_id == tenant_id, MessageSendAttempt.message_id == message_id,
    ).order_by(MessageSendAttempt.attempt_number))).all())
