from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Membership


async def get_membership(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
    active_only: bool = False,
) -> Membership | None:
    statement = select(Membership).where(
        Membership.user_id == user_id,
        Membership.tenant_id == tenant_id,
    )
    if active_only:
        statement = statement.where(Membership.status == "active")
    return await session.scalar(statement)


async def list_memberships(
    session: AsyncSession,
    *,
    user_id: UUID,
    active_only: bool = False,
) -> list[Membership]:
    statement = select(Membership).where(Membership.user_id == user_id)
    if active_only:
        statement = statement.where(Membership.status == "active")
    result = await session.scalars(statement.order_by(Membership.invited_at, Membership.id))
    return list(result)
