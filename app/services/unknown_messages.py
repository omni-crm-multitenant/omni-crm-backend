from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Conversation, Message
from app.services.audit import write_audit_event
from app.services.authorization import AuthorizationDenied


class UnknownMessageError(ValueError):
    pass


async def resolve_unknown_message(
    session: AsyncSession,
    *,
    context: TenantContext,
    message_id: UUID,
    receipt_provider_message_id: str | None = None,
    resend: bool = False,
    duplicate_risk_acknowledged: bool = False,
) -> Message:
    message = await session.scalar(select(Message).where(
        Message.id == message_id, Message.tenant_id == context.tenant_id,
    ).with_for_update())
    if message is None:
        raise LookupError("MESSAGE_NOT_FOUND")
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == message.conversation_id, Conversation.tenant_id == context.tenant_id,
    ))
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if context.role == "agente_comercial" and conversation.assigned_user_id != context.user_id:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")
    if message.status != "unknown":
        raise UnknownMessageError("MESSAGE_IS_NOT_UNKNOWN")
    if receipt_provider_message_id:
        message.provider_message_id = receipt_provider_message_id
        message.status = "sent"
        message.message_metadata = {**message.message_metadata, "unknown_resolution": "verified_receipt"}
        action = "message.unknown_resolved"
    elif resend and duplicate_risk_acknowledged:
        message.status = "queued"
        message.message_metadata = {
            **message.message_metadata,
            "unknown_resolution": "explicit_resend",
            "duplicate_risk_acknowledged": True,
        }
        action = "message.unknown_resend_authorized"
    else:
        raise UnknownMessageError("RESOLUTION_REQUIRES_RECEIPT_OR_DUPLICATE_RISK_ACK")
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action=action, resource_type="message", resource_id=message.id,
        metadata={"provider_message_id": receipt_provider_message_id, "resend": resend},
    )
    await session.flush()
    return message
