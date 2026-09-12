from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_action_attempt import AutomationActionAttempt
from app.models.automation_execution import AutomationExecution


async def claim_action_attempt(
    session: AsyncSession, *, tenant_id: UUID, execution_id: UUID, action_index: int,
    idempotency_key: str, lease_seconds: int = 60,
) -> AutomationActionAttempt | None:
    attempt = await session.scalar(select(AutomationActionAttempt).where(
        AutomationActionAttempt.tenant_id == tenant_id,
        AutomationActionAttempt.execution_id == execution_id,
        AutomationActionAttempt.action_index == action_index,
    ).with_for_update())
    now = datetime.now(UTC)
    if attempt is not None:
        if attempt.status == "succeeded":
            return attempt
        if attempt.status == "processing" and attempt.lease_expires_at and attempt.lease_expires_at > now:
            return None
    else:
        attempt = AutomationActionAttempt(
            tenant_id=tenant_id, execution_id=execution_id, action_index=action_index,
            idempotency_key=idempotency_key,
        )
        session.add(attempt)
    attempt.status = "processing"
    attempt.lease_token = uuid4().hex
    attempt.lease_expires_at = now + timedelta(seconds=lease_seconds)
    await session.flush()
    return attempt


async def finish_action_attempt(
    session: AsyncSession, *, attempt: AutomationActionAttempt, lease_token: str,
    status: str, result: dict | None = None,
) -> bool:
    if attempt.lease_token != lease_token or status not in {"succeeded", "failed", "unknown", "cancelled"}:
        return False
    attempt.status = status
    attempt.result = result or {}
    attempt.lease_expires_at = None
    await session.flush()
    return True


async def claim_execution(session: AsyncSession, *, tenant_id: UUID, execution_id: UUID, lease_seconds: int = 60) -> str | None:
    execution = await session.scalar(select(AutomationExecution).where(
        AutomationExecution.id == execution_id, AutomationExecution.tenant_id == tenant_id,
    ).with_for_update())
    if execution is None:
        return None
    now = datetime.now(UTC)
    if execution.status == "processing" and execution.lease_expires_at and execution.lease_expires_at > now:
        return None
    if execution.status in {"success", "blocked", "dead_letter"}:
        return None
    if execution.next_attempt_at and execution.next_attempt_at > now:
        return None
    token = uuid4().hex
    execution.status = "processing"
    execution.attempts += 1
    execution.lease_token = token
    execution.lease_expires_at = now + timedelta(seconds=lease_seconds)
    execution.started_at = execution.started_at or now
    await session.flush()
    return token


async def complete_execution(session: AsyncSession, *, tenant_id: UUID, execution_id: UUID, lease_token: str, status: str, result: dict | None = None) -> bool:
    execution = await session.scalar(select(AutomationExecution).where(
        AutomationExecution.id == execution_id, AutomationExecution.tenant_id == tenant_id,
        AutomationExecution.lease_token == lease_token,
    ).with_for_update())
    if execution is None:
        return False
    execution.status = status
    execution.result = result or {}
    execution.lease_expires_at = None
    execution.finished_at = datetime.now(UTC)
    await session.flush()
    return True


BACKOFF_SECONDS = (5, 30, 120, 600, 1800)


async def schedule_execution_retry(session: AsyncSession, *, execution: AutomationExecution, result: dict, unknown: bool = False) -> None:
    if unknown:
        execution.status = "partial"
        execution.result = {**result, "awaiting_reconciliation": True}
        await session.flush()
        return
    index = min(max(execution.attempts - 1, 0), len(BACKOFF_SECONDS) - 1)
    execution.status = "failed" if execution.attempts < len(BACKOFF_SECONDS) else "dead_letter"
    execution.result = result
    execution.next_attempt_at = datetime.now(UTC) + timedelta(seconds=BACKOFF_SECONDS[index])
    await session.flush()
