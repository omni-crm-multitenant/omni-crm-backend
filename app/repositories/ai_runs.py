from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiRun


async def start_ai_run(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    profile_id: UUID,
    profile_version: int,
    trigger_message_id: UUID,
    provider: str,
    model: str,
    control_version: int,
) -> AiRun:
    existing = await session.scalar(select(AiRun).where(
        AiRun.tenant_id == tenant_id,
        AiRun.conversation_id == conversation_id,
        AiRun.trigger_message_id == trigger_message_id,
    ))
    if existing is not None:
        return existing
    run = AiRun(
        tenant_id=tenant_id, conversation_id=conversation_id, profile_id=profile_id,
        profile_version=profile_version, trigger_message_id=trigger_message_id,
        provider=provider, model=model, status="pending", control_version=control_version,
    )
    session.add(run)
    await session.flush()
    return run


async def finish_ai_run(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    run_id: UUID,
    status: str,
    latency_ms: int | None = None,
    token_usage: dict[str, Any] | None = None,
) -> AiRun | None:
    run = await session.scalar(select(AiRun).where(AiRun.id == run_id, AiRun.tenant_id == tenant_id).with_for_update())
    if run is None:
        return None
    run.status = status
    run.latency_ms = latency_ms
    if token_usage is not None:
        run.token_usage = token_usage
    run.completed_at = datetime.now(UTC)
    await session.flush()
    return run


async def recover_ai_run(session: AsyncSession, *, tenant_id: UUID, run_id: UUID) -> AiRun | None:
    run = await session.scalar(select(AiRun).where(AiRun.id == run_id, AiRun.tenant_id == tenant_id).with_for_update())
    if run is None or run.status in {"success", "transferred", "cancelled"}:
        return run
    run.status = "error"
    run.completed_at = datetime.now(UTC)
    await session.flush()
    return run
