from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.jobs import Job


router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    id: UUID
    type: str
    status: str
    progress: int
    result: dict | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


_SECRET_KEYS = {"secret", "token", "password", "credential", "credentials", "api_key", "access_token", "refresh_token"}


def _redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if any(part in key.lower() for part in _SECRET_KEYS) else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    job = await session.scalar(select(Job).where(Job.id == job_id, Job.tenant_id == context.tenant_id))
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "JOB_NOT_FOUND"})
    return JobResponse(
        id=job.id, type=job.type, status=job.status, progress=job.progress,
        result=_redact(job.result), error_code=job.error_code,
        created_at=job.created_at, finished_at=job.finished_at,
    )
