from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attribution import Attribution
from app.models.crm import Consent, Contact, ContactIdentity, Conversation, Message
from app.models.graph_checkpoint import GraphCheckpoint
from app.models.operations import TenantSettings


def _value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def build_contact_export(session: AsyncSession, tenant_id: UUID, contact_id: UUID) -> dict[str, Any]:
    from app.models.opportunities import Opportunity
    contact = await session.scalar(select(Contact).where(
        Contact.tenant_id == tenant_id, Contact.id == contact_id,
    ))
    if contact is None:
        raise LookupError("CONTACT_NOT_FOUND")
    identities = list((await session.scalars(select(ContactIdentity).where(
        ContactIdentity.tenant_id == tenant_id, ContactIdentity.contact_id == contact_id,
    ))).all())
    conversations = list((await session.scalars(select(Conversation).where(
        Conversation.tenant_id == tenant_id, Conversation.contact_id == contact_id,
    ))).all())
    conversation_ids = [row.id for row in conversations]
    messages = list((await session.scalars(select(Message).where(
        Message.tenant_id == tenant_id, Message.conversation_id.in_(conversation_ids),
    ))).all()) if conversation_ids else []
    opportunities = list((await session.scalars(select(Opportunity).where(
        Opportunity.tenant_id == tenant_id, Opportunity.contact_id == contact_id,
    ))).all())
    from app.models.tasks import Task
    tasks = list((await session.scalars(select(Task).where(
        Task.tenant_id == tenant_id, Task.contact_id == contact_id,
    ))).all())
    consents = list((await session.scalars(select(Consent).where(
        Consent.tenant_id == tenant_id, Consent.contact_id == contact_id,
    ))).all())
    attributions = list((await session.scalars(select(Attribution).where(
        Attribution.tenant_id == tenant_id, Attribution.contact_id == contact_id,
    ))).all())
    return {
        "contact": {key: _value(getattr(contact, key)) for key in ("id", "name", "phone", "email", "source_channel", "owner_user_id", "status", "tags", "custom_fields", "created_at", "updated_at")},
        "identities": [{key: _value(getattr(row, key)) for key in ("id", "channel_asset_id", "external_user_id", "display_name", "last_seen_at", "identity_metadata")} for row in identities],
        "conversations": [{key: _value(getattr(row, key)) for key in ("id", "channel", "status", "ai_mode", "assigned_user_id", "last_message_at", "created_at", "updated_at")} for row in conversations],
        "messages": [{key: _value(getattr(row, key)) for key in ("id", "conversation_id", "channel", "direction", "author_type", "author_user_id", "body_text", "status", "occurred_at", "created_at")} for row in messages],
        "opportunities": [{key: _value(getattr(row, key)) for key in ("id", "pipeline_id", "stage_id", "owner_user_id", "amount", "currency", "loss_reason", "expected_close_at", "custom_fields", "created_at", "updated_at")} for row in opportunities],
        "tasks": [{key: _value(getattr(row, key)) for key in ("id", "title", "description", "assigned_user_id", "due_at", "priority", "status", "source", "created_at", "updated_at")} for row in tasks],
        "consents": [{key: _value(getattr(row, key)) for key in ("id", "channel", "purpose", "status", "source", "captured_at", "revoked_at")} for row in consents],
        "attributions": [{key: _value(getattr(row, key)) for key in ("id", "campaign_id", "ad_set_id", "ad_id", "source", "confidence", "raw_metadata", "created_at")} for row in attributions],
    }


async def logically_erase_contact(session: AsyncSession, *, tenant_id: UUID, contact_id: UUID, requested_at: datetime | None = None) -> Contact:
    contact = await session.scalar(select(Contact).where(
        Contact.tenant_id == tenant_id, Contact.id == contact_id,
    ).with_for_update())
    if contact is None:
        raise LookupError("CONTACT_NOT_FOUND")
    now = requested_at or datetime.now(UTC)
    contact.status = "deleted"
    contact.deleted_at = now
    contact.erasure_requested_at = now
    await session.execute(update(ContactIdentity).where(
        ContactIdentity.tenant_id == tenant_id, ContactIdentity.contact_id == contact_id,
    ).values(external_user_id=f"erased:{contact_id}:{now.timestamp()}"))
    await session.flush()
    return contact


async def purge_erased_contacts(session: AsyncSession, *, now: datetime | None = None, limit: int = 100) -> int:
    now = now or datetime.now(UTC)
    rows = list((await session.scalars(select(Contact).where(
        Contact.status == "deleted", Contact.erasure_requested_at.is_not(None),
    ).limit(limit).with_for_update())).all())
    purged = 0
    for contact in rows:
        settings = await session.get(TenantSettings, contact.tenant_id)
        retention_days = int(((settings.contact_info if settings else {}) or {}).get("retention_days", 365))
        if contact.erasure_requested_at > now - timedelta(days=retention_days):
            continue
        await session.execute(update(Message).where(Message.tenant_id == contact.tenant_id, Message.conversation_id.in_(select(Conversation.id).where(Conversation.tenant_id == contact.tenant_id, Conversation.contact_id == contact.id))).values(body_text=None, message_metadata={}))
        await session.execute(update(GraphCheckpoint).where(GraphCheckpoint.tenant_id == contact.tenant_id, GraphCheckpoint.conversation_id.in_(select(Conversation.id).where(Conversation.tenant_id == contact.tenant_id, Conversation.contact_id == contact.id))).values(state={}))
        await session.execute(update(ContactIdentity).where(ContactIdentity.tenant_id == contact.tenant_id, ContactIdentity.contact_id == contact.id).values(external_user_id=f"purged:{contact.id}", display_name=None, identity_metadata={}))
        contact.name = "Contacto eliminado"
        contact.phone = None
        contact.email = None
        contact.tags = []
        contact.custom_fields = {}
        purged += 1
    await session.flush()
    return purged
