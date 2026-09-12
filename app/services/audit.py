from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sanitization import sanitize_metadata
from app.models.operations import AuditEvent


async def write_audit_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_type: str,
    action: str,
    resource_type: str,
    actor_user_id: UUID | None = None,
    resource_id: str | UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        sanitized_metadata=sanitize_metadata(metadata or {}),
    )
    session.add(event)
    await session.flush()
    return event
