from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Conversation


async def propagate_opportunity_assignment(
    session: AsyncSession, *, tenant_id: UUID, contact_id: UUID, owner_user_id: UUID
) -> int:
    conversations = list((await session.scalars(select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.contact_id == contact_id,
        Conversation.status.in_(("open", "pending")),
    ).with_for_update())).all())
    for conversation in conversations:
        conversation.assigned_user_id = owner_user_id
    await session.flush()
    return len(conversations)
