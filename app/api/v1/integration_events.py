from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.tenant_context import TenantContext
from app.models.operations import WebhookEvent
from app.services.audit import write_audit_event
from app.services.authorization import require_roles


router = APIRouter(prefix="/integration-events", tags=["integration-events"])


class RedriveResponse(BaseModel):
    id: UUID
    status: str
    event_key: str


@router.post("/{event_id}/redrive", response_model=RedriveResponse)
async def redrive_integration_event(
    event_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> RedriveResponse:
    event = await session.scalar(select(WebhookEvent).where(
        WebhookEvent.id == event_id, WebhookEvent.tenant_id == context.tenant_id,
    ).with_for_update())
    if event is None:
        raise HTTPException(status_code=404, detail={"code": "INTEGRATION_EVENT_NOT_FOUND"})
    if event.status != "dead_letter":
        raise HTTPException(status_code=409, detail={"code": "EVENT_NOT_SAFE_TO_REDRIVE"})
    event.status = "received"
    event.attempts = 0
    event.error_code = None
    event.next_attempt_at = datetime.now(UTC)
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="integration_event.redriven", resource_type="webhook_event", resource_id=event.id,
        metadata={"event_key": event.event_key},
    )
    await session.flush()
    return RedriveResponse(id=event.id, status=event.status, event_key=event.event_key)
