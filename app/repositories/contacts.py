from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.crm import Contact
from app.services.custom_fields import validate_custom_field_payload


class ContactNotFound(LookupError):
    pass


async def create_contact(
    session: AsyncSession,
    context: TenantContext,
    *,
    name: str,
    phone: str | None = None,
    email: str | None = None,
    source_channel: str | None = None,
    source_campaign_id: UUID | None = None,
    owner_user_id: UUID | None = None,
    tags: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> Contact:
    values = custom_fields or {}
    await validate_custom_field_payload(
        session,
        tenant_id=context.tenant_id,
        entity_type="contact",
        values=values,
        require_all=True,
    )
    contact = Contact(
        tenant_id=context.tenant_id,
        name=name.strip(),
        phone=phone,
        email=email.strip().lower() if email else None,
        source_channel=source_channel,
        source_campaign_id=source_campaign_id,
        owner_user_id=owner_user_id,
        tags=tags or [],
        custom_fields=values,
    )
    session.add(contact)
    await session.flush()
    return contact


async def update_contact(
    session: AsyncSession,
    context: TenantContext,
    contact_id: UUID,
    *,
    custom_fields: dict[str, Any] | None = None,
    **changes: Any,
) -> Contact:
    contact = await session.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == context.tenant_id)
    )
    if contact is None:
        raise ContactNotFound
    if custom_fields is not None:
        merged = {**contact.custom_fields, **custom_fields}
        await validate_custom_field_payload(
            session,
            tenant_id=context.tenant_id,
            entity_type="contact",
            values=merged,
            require_all=True,
        )
        contact.custom_fields = merged
    allowed = {"name", "phone", "email", "source_channel", "source_campaign_id", "owner_user_id", "status", "tags"}
    for key, value in changes.items():
        if key not in allowed:
            raise ValueError(f"unsupported contact field: {key}")
        setattr(contact, key, value)
    await session.flush()
    return contact
