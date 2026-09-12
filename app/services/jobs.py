from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import Job


_ERROR_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,119}$")


def _safe_error_code(value: str | None) -> str:
    return value if value and _ERROR_CODE.fullmatch(value) else "WORKER_FAILED"


async def create_job(session: AsyncSession, tenant_id: UUID, type: str) -> UUID:
    job = Job(tenant_id=tenant_id, type=type, status="queued", progress=0)
    session.add(job)
    await session.flush()
    return job.id


async def update_job_progress(
    session: AsyncSession,
    job_id: UUID,
    *,
    progress: int,
    result: dict[str, Any] | None = None,
) -> Job:
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise LookupError("JOB_NOT_FOUND")
    job.progress = max(0, min(100, progress))
    if result is not None:
        job.result = result
    await session.flush()
    return job


@asynccontextmanager
async def run_job(
    session: AsyncSession,
    job_id: UUID,
    *,
    error_code: str | None = None,
) -> AsyncIterator[Job]:
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None:
        raise LookupError("JOB_NOT_FOUND")
    if job.status not in {"queued", "running"}:
        raise ValueError("JOB_NOT_RUNNABLE")
    job.status = "running"
    job.progress = max(job.progress, 0)
    await session.flush()
    try:
        yield job
    except Exception as exc:
        job.status = "failed"
        job.error_code = _safe_error_code(getattr(exc, "error_code", None) or error_code)
        job.finished_at = datetime.now(UTC)
        await session.flush()
        raise
    else:
        job.status = "succeeded"
        job.progress = 100
        job.finished_at = datetime.now(UTC)
        await session.flush()


__all__ = ["create_job", "run_job", "update_job_progress"]
