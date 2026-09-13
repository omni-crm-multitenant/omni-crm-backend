from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.identity import Membership


Role = Literal["administrador", "supervisor", "agente_comercial"]
ResourceAction = Literal["read", "write", "takeover", "reassign"]


class TenantAssignedResource(Protocol):
    tenant_id: UUID
    assignee_membership_id: UUID | None


class AuthorizationDenied(PermissionError):
    def __init__(self, code: str = "FORBIDDEN") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ResourceScope:
    tenant_id: UUID
    assignee_membership_id: UUID | None


def authorize_assigned_resource(
    context: TenantContext,
    resource: TenantAssignedResource | ResourceScope,
    *,
    action: ResourceAction,
) -> None:
    if resource.tenant_id != context.tenant_id:
        raise AuthorizationDenied("CROSS_TENANT_ACCESS_DENIED")
    if context.role in {"administrador", "supervisor"}:
        return
    if action == "reassign":
        raise AuthorizationDenied("REASSIGNMENT_FORBIDDEN")
    if resource.assignee_membership_id != context.membership_id:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")


async def validate_assignee_membership(
    session: AsyncSession,
    context: TenantContext,
    assignee_membership_id: UUID,
) -> Membership:
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == assignee_membership_id,
            Membership.tenant_id == context.tenant_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise AuthorizationDenied("INVALID_ASSIGNEE")
    return membership
