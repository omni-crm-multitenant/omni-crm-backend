from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Conversation, Message
from app.models.handoffs import ConversationTransfer
from app.services.handoff import accept_handoff
from app.services.audit import write_audit_event
from app.services.authorization import AuthorizationDenied


async def set_conversation_mode(
    session: AsyncSession, *, context: TenantContext, conversation_id: UUID, mode: str,
) -> Conversation:
    if mode not in {"active", "human"}:
        raise ValueError("INVALID_AI_MODE")
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.tenant_id == context.tenant_id,
    ).with_for_update())
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if context.role == "agente_comercial" and conversation.assigned_user_id != context.user_id:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")
    conversation.ai_mode = mode
    conversation.control_version += 1
    if mode == "human":
        await session.execute(update(Message).where(
            Message.tenant_id == context.tenant_id, Message.conversation_id == conversation_id,
            Message.author_type == "ai", Message.status == "queued",
        ).values(status="cancelled"))
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="conversation.ai_mode_changed", resource_type="conversation", resource_id=conversation.id,
        metadata={"mode": mode, "control_version": conversation.control_version},
    )
    await session.flush()
    return conversation


async def takeover_conversation(session: AsyncSession, *, context: TenantContext, conversation_id: UUID) -> Conversation:
    conversation = await set_conversation_mode(session, context=context, conversation_id=conversation_id, mode="human")
    transfer = await session.scalar(select(ConversationTransfer).where(
        ConversationTransfer.tenant_id == context.tenant_id,
        ConversationTransfer.conversation_id == conversation_id,
        ConversationTransfer.status == "pending",
    ).with_for_update())
    if transfer is not None:
        await accept_handoff(session, transfer_id=transfer.id, context=context)
    return conversation
