from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Conversation, Message
from app.services.message_authors import MessageAuthor
from app.services.authorization import AuthorizationDenied
from app.repositories.messages import create_message
from app.services.outbound_policy import assert_proactive_send_allowed


class IdempotencyConflict(ValueError):
    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


def _request_hash(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()


async def send_outbound_message(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    body_text: str,
    author: MessageAuthor,
    purpose: str = "marketing",
    idempotency_key: str | None = None,
    consent_required: bool = True,
) -> Message:
    """Shared automation/AI entry point; proactive sends must prove consent."""
    conversation: Conversation | None
    if consent_required:
        conversation = await assert_proactive_send_allowed(
            session, tenant_id=tenant_id, conversation_id=conversation_id, purpose=purpose,
        )
    else:
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ))
        if conversation is None:
            raise LookupError("CONVERSATION_NOT_FOUND")
    assert conversation is not None
    return await create_message(
        session, tenant_id=tenant_id, conversation_id=conversation.id,
        channel_asset_id=conversation.channel_asset_id, channel=conversation.channel,
        direction="outbound", status="queued", author=author, body_text=body_text,
        client_idempotency_key=idempotency_key,
        client_request_hash=_request_hash(body_text) if idempotency_key else None,
    )


async def create_send_intent(
    session: AsyncSession,
    *,
    context: TenantContext,
    conversation_id: UUID,
    body_text: str,
    idempotency_key: str | None = None,
) -> Message:
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.tenant_id == context.tenant_id,
    ).with_for_update())
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if context.role == "agente_comercial" and conversation.assigned_user_id != context.user_id:
        raise AuthorizationDenied("RESOURCE_NOT_ASSIGNED")
    request_hash = _request_hash(body_text)
    if idempotency_key:
        existing = await session.scalar(select(Message).where(
            Message.tenant_id == context.tenant_id,
            Message.conversation_id == conversation.id,
            Message.client_idempotency_key == idempotency_key,
        ).with_for_update())
        if existing is not None:
            if existing.client_request_hash != request_hash:
                raise IdempotencyConflict()
            return existing
    return await create_message(
        session,
        tenant_id=context.tenant_id,
        conversation_id=conversation.id,
        channel_asset_id=conversation.channel_asset_id,
        channel=conversation.channel,
        direction="outbound",
        status="queued",
        author=MessageAuthor.agent(context.user_id),
        body_text=body_text,
        client_idempotency_key=idempotency_key,
        client_request_hash=request_hash if idempotency_key else None,
    )
