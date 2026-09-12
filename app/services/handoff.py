from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Conversation, Message
from app.models.handoffs import ConversationTransfer
from app.services.audit import write_audit_event
from app.services.authorization import AuthorizationDenied


class HandoffError(ValueError):
    pass


TRANSFER_REASONS = {
    "explicit_request", "purchase_intent", "low_confidence", "complex",
    "tool_failure", "limit_exceeded", "needs_human", "pricing", "complaint", "policy", "other",
}


async def handoff(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    trigger_id: UUID,
    reason: str,
    context: TenantContext | None = None,
    tenant_id: UUID | None = None,
    recipient_user_id: UUID | None = None,
    actor_type: str = "ai",
) -> ConversationTransfer:
    resolved_tenant_id = context.tenant_id if context else tenant_id
    if resolved_tenant_id is None:
        raise ValueError("TENANT_REQUIRED")
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.tenant_id == resolved_tenant_id,
    ).with_for_update())
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if context and context.role == "agente_comercial" and conversation.assigned_user_id != context.user_id:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")
    existing = await session.scalar(select(ConversationTransfer).where(
        ConversationTransfer.tenant_id == resolved_tenant_id,
        ConversationTransfer.trigger_id == trigger_id,
    ))
    if existing is not None:
        return existing
    pending = await session.scalar(select(ConversationTransfer).where(
        ConversationTransfer.tenant_id == resolved_tenant_id,
        ConversationTransfer.conversation_id == conversation_id,
        ConversationTransfer.status == "pending",
    ))
    if pending is not None:
        return pending
    conversation.ai_mode = "handoff_pending"
    conversation.control_version += 1
    await session.execute(update(Message).where(
        Message.tenant_id == resolved_tenant_id, Message.conversation_id == conversation_id,
        Message.author_type == "ai", Message.status == "queued",
    ).values(status="cancelled"))
    transfer = ConversationTransfer(
        tenant_id=resolved_tenant_id, conversation_id=conversation_id,
        trigger_id=trigger_id, reason=reason, recipient_user_id=recipient_user_id,
    )
    session.add(transfer)
    await session.flush()
    await write_audit_event(
        session, tenant_id=resolved_tenant_id, actor_type=actor_type,
        actor_user_id=context.user_id if context else None,
        action="conversation.handoff_requested", resource_type="conversation",
        resource_id=conversation_id, metadata={"transfer_id": str(transfer.id), "reason": reason},
    )
    return transfer


async def accept_handoff(
    session: AsyncSession, *, transfer_id: UUID, context: TenantContext,
) -> ConversationTransfer:
    transfer = await session.scalar(select(ConversationTransfer).where(
        ConversationTransfer.id == transfer_id, ConversationTransfer.tenant_id == context.tenant_id,
    ).with_for_update())
    if transfer is None:
        raise LookupError("TRANSFER_NOT_FOUND")
    if transfer.status != "pending":
        return transfer
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == transfer.conversation_id, Conversation.tenant_id == context.tenant_id,
    ).with_for_update())
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if context.role == "agente_comercial" and conversation.assigned_user_id not in {None, context.user_id}:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")
    transfer.status = "accepted"
    transfer.accepted_at = datetime.now(UTC)
    conversation.ai_mode = "human"
    conversation.assigned_user_id = transfer.recipient_user_id or context.user_id
    conversation.control_version += 1
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="conversation.handoff_accepted", resource_type="conversation",
        resource_id=conversation.id, metadata={"transfer_id": str(transfer.id)},
    )
    await session.flush()
    return transfer
