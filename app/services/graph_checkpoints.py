from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_checkpoint import GraphCheckpoint


async def save_checkpoint(session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, state: dict, version: int) -> GraphCheckpoint:
    checkpoint = await session.scalar(select(GraphCheckpoint).where(
        GraphCheckpoint.tenant_id == tenant_id, GraphCheckpoint.conversation_id == conversation_id,
    ).with_for_update())
    if checkpoint is None:
        checkpoint = GraphCheckpoint(tenant_id=tenant_id, conversation_id=conversation_id, state=state, version=version)
        session.add(checkpoint)
    else:
        checkpoint.state = state
        checkpoint.version = version
    await session.flush()
    return checkpoint


async def load_checkpoint(session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID) -> GraphCheckpoint | None:
    return await session.scalar(select(GraphCheckpoint).where(
        GraphCheckpoint.tenant_id == tenant_id, GraphCheckpoint.conversation_id == conversation_id,
    ))
