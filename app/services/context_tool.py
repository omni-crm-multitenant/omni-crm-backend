from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Contact, Conversation
from app.models.opportunities import Opportunity
from app.services.agent_tools import CONTACT_CONTEXT_FIELDS, OPPORTUNITY_CONTEXT_FIELDS


def _allowed_values(entity: Any, fields: frozenset[str]) -> dict[str, Any]:
    return {field: getattr(entity, field) for field in fields if hasattr(entity, field)}


def build_read_context_tool(session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, opportunity_id: UUID | None = None):
    async def read_contact_context() -> dict[str, Any]:
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ))
        if conversation is None:
            return {"contact": None, "opportunity": None}
        contact = await session.scalar(select(Contact).where(
            Contact.id == conversation.contact_id, Contact.tenant_id == tenant_id,
        ))
        opportunity = None
        if opportunity_id is not None:
            opportunity = await session.scalar(select(Opportunity).where(
                Opportunity.id == opportunity_id, Opportunity.tenant_id == tenant_id,
                Opportunity.contact_id == conversation.contact_id,
            ))
        return {
            "contact": _allowed_values(contact, CONTACT_CONTEXT_FIELDS) if contact else None,
            "opportunity": _allowed_values(opportunity, OPPORTUNITY_CONTEXT_FIELDS) if opportunity else None,
        }

    return read_contact_context
