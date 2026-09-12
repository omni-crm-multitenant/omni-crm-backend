from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.services.kpi import first_response_metrics


router = APIRouter(prefix="/kpi", tags=["kpi"])


class FirstResponseMetrics(BaseModel):
    count: int
    median_ms: float | None
    p90_ms: float | None
    percent_answered_within_60s: float
    percent_resolved_by_ai: float


@router.get("/first-response", response_model=FirstResponseMetrics)
async def first_response(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    channel: str | None = Query(default=None),
    campaign_id: UUID | None = Query(default=None),
    responder_type: str | None = Query(default=None),
    responder_user_id: UUID | None = Query(default=None),
    ai_model: str | None = Query(default=None),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FirstResponseMetrics:
    return FirstResponseMetrics(**await first_response_metrics(
        session, tenant_id=context.tenant_id, start=start, end=end,
        channel=channel, campaign_id=campaign_id, responder_type=responder_type,
        responder_user_id=responder_user_id, ai_model=ai_model,
    ))
