from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Contact
from app.models.identity import ChannelAsset
from app.repositories.contact_identities import get_contact_identity, upsert_contact_identity
from app.services.normalization import normalize_email, normalize_phone


class AmbiguousContactMatch(ValueError):
    pass


@dataclass(frozen=True)
class ContactResolution:
    contact: Contact
    matched_existing: bool
    identity_created: bool


async def find_or_create_contact(
    session: AsyncSession, *, tenant_id: UUID, channel: str, external_user_id: str,
    phone: str | None = None, email: str | None = None, name: str | None = None,
    channel_asset_id: UUID | None = None,
) -> Contact:
    phone = normalize_phone(phone) if phone else None
    email = normalize_email(email) if email else None
    if channel_asset_id is None:
        asset_ids = list((await session.scalars(select(ChannelAsset.id).where(
            ChannelAsset.tenant_id == tenant_id, ChannelAsset.channel == channel, ChannelAsset.status == "connected",
        ))).all())
        if len(asset_ids) != 1:
            raise ValueError("channel_asset_id is required when channel has zero or multiple assets")
        channel_asset_id = asset_ids[0]
    identity = await get_contact_identity(session, tenant_id=tenant_id, channel_asset_id=channel_asset_id, external_user_id=external_user_id)
    if identity is not None:
        contact = await session.scalar(select(Contact).where(Contact.tenant_id == tenant_id, Contact.id == identity.contact_id, Contact.status != "deleted", Contact.deleted_at.is_(None)))
        if contact is not None:
            return contact
    predicates = []
    if phone:
        predicates.append(Contact.phone == phone)
    if email:
        predicates.append(Contact.email == email)
    matches = list((await session.scalars(select(Contact).where(Contact.tenant_id == tenant_id, Contact.status != "deleted", Contact.deleted_at.is_(None), or_(*predicates)))).all()) if predicates else []
    if len({contact.id for contact in matches}) > 1:
        raise AmbiguousContactMatch("ambiguous contact identity")
    if len(matches) == 1:
        current = matches[0]
        if (phone and current.phone and current.phone != phone) or (email and current.email and current.email != email):
            raise AmbiguousContactMatch("phone and email identify conflicting contact data")
    contact = matches[0] if matches else Contact(
        tenant_id=tenant_id, name=(name or "Contacto").strip(), phone=phone, email=email,
        source_channel=channel, tags=[], custom_fields={},
    )
    if not matches:
        session.add(contact)
        await session.flush()
    await upsert_contact_identity(
        session, tenant_id=tenant_id, contact_id=contact.id, channel_asset_id=channel_asset_id,
        external_user_id=external_user_id, display_name=name,
    )
    return contact


async def find_or_create_contact_with_decision(
    session: AsyncSession, **kwargs
) -> ContactResolution:
    existing = await get_contact_identity(
        session,
        tenant_id=kwargs["tenant_id"],
        channel_asset_id=kwargs.get("channel_asset_id"),
        external_user_id=kwargs["external_user_id"],
    ) if kwargs.get("channel_asset_id") else None
    contact = await find_or_create_contact(session, **kwargs)
    return ContactResolution(contact=contact, matched_existing=existing is not None, identity_created=existing is None)
