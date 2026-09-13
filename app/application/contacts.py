from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import CursorPage, paginate
from app.core.tenant_context import TenantContext
from app.models.crm import Contact
from app.services.audit import write_audit_event
from app.services.custom_fields import validate_custom_field_payload
from app.services.normalization import normalize_email, normalize_phone


@dataclass(frozen=True)
class CreateContactCommand:
    name: str
    phone: str | None = None
    email: str | None = None
    source_channel: str | None = None
    owner_user_id: UUID | None = None
    tags: list[str] = field(default_factory=list)
    custom_fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UpdateContactCommand:
    values: dict


@dataclass(frozen=True)
class ContactListQuery:
    status: str | None = None
    owner_user_id: UUID | None = None
    tag: str | None = None
    source_channel: str | None = None
    custom_field: str | None = None
    custom_value: str | None = None
    cursor: str | None = None
    limit: int = 50


async def create_contact(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateContactCommand,
) -> Contact:
    await validate_custom_field_payload(
        session,
        tenant_id=context.tenant_id,
        entity_type="contact",
        values=command.custom_fields,
        require_all=False,
    )
    contact = Contact(
        tenant_id=context.tenant_id,
        name=command.name,
        phone=normalize_phone(command.phone) if command.phone else None,
        email=normalize_email(command.email) if command.email else None,
        source_channel=command.source_channel,
        owner_user_id=command.owner_user_id,
        tags=command.tags,
        custom_fields=command.custom_fields,
    )
    session.add(contact)
    await session.flush()
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.created",
        resource_type="contact",
        resource_id=contact.id,
    )
    return contact


async def list_contacts(
    session: AsyncSession,
    *,
    context: TenantContext,
    query: ContactListQuery,
) -> CursorPage:
    statement = select(Contact).where(
        Contact.tenant_id == context.tenant_id,
        Contact.status != "deleted",
    )
    if query.status:
        statement = statement.where(Contact.status == query.status)
    if query.owner_user_id:
        statement = statement.where(Contact.owner_user_id == query.owner_user_id)
    if query.tag:
        statement = statement.where(Contact.tags.contains([query.tag]))
    if query.source_channel:
        statement = statement.where(Contact.source_channel == query.source_channel)
    if query.custom_field and query.custom_value is not None:
        statement = statement.where(
            Contact.custom_fields[query.custom_field].as_string() == query.custom_value
        )
    return await paginate(
        session,
        statement,
        query.cursor,
        query.limit,
        (Contact.created_at, Contact.id),
    )


async def update_contact(
    session: AsyncSession,
    *,
    context: TenantContext,
    contact: Contact,
    command: UpdateContactCommand,
) -> Contact:
    if contact.tenant_id != context.tenant_id:
        raise LookupError("CONTACT_NOT_FOUND")
    values = dict(command.values)
    if "custom_fields" in values and values["custom_fields"] is not None:
        await validate_custom_field_payload(
            session,
            tenant_id=context.tenant_id,
            entity_type="contact",
            values=values["custom_fields"],
            require_all=False,
        )
        contact.custom_fields = {**contact.custom_fields, **values.pop("custom_fields")}
    if "phone" in values and values["phone"]:
        values["phone"] = normalize_phone(values["phone"])
    if "email" in values and values["email"]:
        values["email"] = normalize_email(values["email"])
    for key, value in values.items():
        setattr(contact, key, value)
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.updated",
        resource_type="contact",
        resource_id=contact.id,
        metadata={"fields": list(command.values)},
    )
    await session.flush()
    return contact


@dataclass(frozen=True)
class ConsentCommand:
    channel: str
    purpose: str
    source: str


async def grant_contact_consent(
    session: AsyncSession,
    *,
    context: TenantContext,
    contact_id: UUID,
    command: ConsentCommand,
):
    from app.models.crm import Consent

    consent = Consent(
        tenant_id=context.tenant_id,
        contact_id=contact_id,
        channel=command.channel,
        purpose=command.purpose,
        status="granted",
        source=command.source,
    )
    session.add(consent)
    await session.flush()
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.consent_granted",
        resource_type="consent",
        resource_id=consent.id,
        metadata={"contact_id": contact_id, "channel": command.channel, "purpose": command.purpose},
    )
    return consent


async def revoke_contact_consent(
    session: AsyncSession,
    *,
    context: TenantContext,
    contact_id: UUID,
    command: ConsentCommand,
):
    from datetime import UTC, datetime
    from app.models.crm import Consent

    revoked_at = datetime.now(UTC)
    consent = Consent(
        tenant_id=context.tenant_id,
        contact_id=contact_id,
        channel=command.channel,
        purpose=command.purpose,
        status="revoked",
        source=command.source,
        captured_at=revoked_at,
        revoked_at=revoked_at,
    )
    session.add(consent)
    await session.flush()
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.consent_revoked",
        resource_type="consent",
        resource_id=consent.id,
        metadata={"contact_id": contact_id, "channel": command.channel, "purpose": command.purpose},
    )
    return consent


async def logically_delete_contact(
    session: AsyncSession,
    *,
    context: TenantContext,
    contact: Contact,
) -> Contact:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    contact.status = "deleted"
    contact.deleted_at = now
    contact.erasure_requested_at = now
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.deleted",
        resource_type="contact",
        resource_id=contact.id,
    )
    await session.flush()
    return contact


async def request_contact_export(
    session: AsyncSession,
    *,
    context: TenantContext,
    contact_id: UUID,
    enqueue_export,
):
    from app.services.jobs import create_job

    job_id = await create_job(session, context.tenant_id, "contact_export")
    enqueue_export(str(context.tenant_id), str(contact_id), str(job_id))
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="contact.export_requested",
        resource_type="contact",
        resource_id=contact_id,
        metadata={"job_id": str(job_id)},
    )
    return job_id
