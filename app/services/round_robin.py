from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import AssignmentRotationState
from app.models.identity import Membership


async def next_round_robin_agent(session: AsyncSession, tenant_id: UUID) -> UUID | None:
    agents = list((await session.scalars(select(Membership).where(
        Membership.tenant_id == tenant_id,
        Membership.role == "agente_comercial",
        Membership.status == "active",
    ).order_by(Membership.user_id.asc()))).all())
    if not agents:
        return None
    state = await session.scalar(select(AssignmentRotationState).where(
        AssignmentRotationState.tenant_id == tenant_id,
    ).with_for_update())
    if state is None:
        state = AssignmentRotationState(tenant_id=tenant_id)
        session.add(state)
        await session.flush()
    ids = [item.user_id for item in agents]
    if state.last_assigned_user_id in ids:
        selected = ids[(ids.index(state.last_assigned_user_id) + 1) % len(ids)]
    else:
        selected = ids[0]
    state.last_assigned_user_id = selected
    await session.flush()
    return selected
