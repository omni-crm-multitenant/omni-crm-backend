from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.pagination import InvalidCursor, paginate
from app.core.sanitization import sanitize_metadata
from app.core.tenant_context import TenantContext
from app.models.operations import AuditEvent
from app.api.dependencies import require_roles


router = APIRouter(prefix="/audit-events", tags=["audit"])


class AuditEventResponse(BaseModel):
    id: UUID
    actor_type: str
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    occurred_at: datetime
    metadata: dict

    @classmethod
    def from_row(cls, row: AuditEvent) -> "AuditEventResponse":
        return cls(
            id=row.id,
            actor_type=row.actor_type,
            actor_user_id=row.actor_user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            occurred_at=row.occurred_at,
            metadata=sanitize_metadata(row.sanitized_metadata),
        )


class AuditEventPage(BaseModel):
    items: list[AuditEventResponse]
    next_cursor: str | None


@router.get("", response_model=AuditEventPage)
async def list_audit_events(
    actor_id: UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> AuditEventPage:
    query = select(AuditEvent).where(AuditEvent.tenant_id == context.tenant_id)
    if actor_id:
        query = query.where(AuditEvent.actor_user_id == actor_id)
    if resource_type:
        query = query.where(AuditEvent.resource_type == resource_type)
    if action:
        query = query.where(AuditEvent.action == action)
    if from_date:
        query = query.where(AuditEvent.occurred_at >= from_date)
    if to_date:
        query = query.where(AuditEvent.occurred_at <= to_date)
    try:
        page = await paginate(
            session, query, cursor, limit, (AuditEvent.occurred_at, AuditEvent.id)
        )
    except (InvalidCursor, ValueError) as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_CURSOR"}) from exc
    return AuditEventPage(
        items=[AuditEventResponse.from_row(row) for row in page.items],
        next_cursor=page.next_cursor,
    )
