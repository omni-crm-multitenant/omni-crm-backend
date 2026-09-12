from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent

MAX_AUTOMATION_DEPTH = 5


@dataclass(frozen=True)
class DomainEvent:
    tenant_id: UUID
    type: str
    resource_id: UUID | str
    payload: dict[str, Any] = field(default_factory=dict)
    depth: int = 0
    originating_rule_id: UUID | None = None
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def descendant(self, *, type: str, resource_id: UUID | str, payload: dict[str, Any], originating_rule_id: UUID | None = None) -> "DomainEvent":
        return DomainEvent(
            tenant_id=self.tenant_id, type=type, resource_id=resource_id, payload=payload,
            depth=self.depth + 1, originating_rule_id=originating_rule_id or self.originating_rule_id,
            event_id=uuid4(),
        )


def can_dispatch_event(event: DomainEvent) -> bool:
    return event.depth <= MAX_AUTOMATION_DEPTH


async def publish_domain_event(session: AsyncSession, event: DomainEvent) -> OutboxEvent:
    row = OutboxEvent(
        id=event.event_id, tenant_id=event.tenant_id, event_type=event.type,
        payload={
            "event_id": str(event.event_id), "tenant_id": str(event.tenant_id),
            "resource_id": str(event.resource_id), "payload": event.payload,
            "depth": event.depth, "originating_rule_id": str(event.originating_rule_id) if event.originating_rule_id else None,
            "occurred_at": event.occurred_at.isoformat(),
        },
    )
    session.add(row)
    await session.flush()
    return row


async def publish_event(session: AsyncSession, event: DomainEvent) -> OutboxEvent:
    """Insert event in caller transaction; relay publishes it later."""
    return await publish_domain_event(session, event)
