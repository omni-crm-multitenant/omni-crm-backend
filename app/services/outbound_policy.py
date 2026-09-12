from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Conversation
from app.services.consent import has_active_consent


class OutboundPolicyError(PermissionError):
    code = "CONSENT_REQUIRED"


async def assert_proactive_send_allowed(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    purpose: str,
) -> Conversation:
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
    ))
    if conversation is None:
        raise LookupError("CONVERSATION_NOT_FOUND")
    if not await has_active_consent(
        session, tenant_id=tenant_id, contact_id=conversation.contact_id,
        channel=conversation.channel, purpose=purpose,
    ):
        raise OutboundPolicyError("active consent required")
    return conversation
