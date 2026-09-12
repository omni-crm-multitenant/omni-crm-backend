from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Contact, ContactIdentity


async def get_contact_identity(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    channel_asset_id: UUID,
    external_user_id: str,
) -> ContactIdentity | None:
    return await session.scalar(
        select(ContactIdentity).where(
            ContactIdentity.tenant_id == tenant_id,
            ContactIdentity.channel_asset_id == channel_asset_id,
            ContactIdentity.external_user_id == external_user_id,
        ).join(Contact, Contact.id == ContactIdentity.contact_id).where(
            Contact.tenant_id == tenant_id, Contact.status != "deleted", Contact.deleted_at.is_(None),
        )
    )


async def upsert_contact_identity(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    channel_asset_id: UUID,
    external_user_id: str,
    display_name: str | None = None,
    metadata: dict | None = None,
    last_seen_at: datetime | None = None,
) -> ContactIdentity:
    identity = await get_contact_identity(
        session,
        tenant_id=tenant_id,
        channel_asset_id=channel_asset_id,
        external_user_id=external_user_id,
    )
    if identity is None:
        identity = ContactIdentity(
            tenant_id=tenant_id,
            contact_id=contact_id,
            channel_asset_id=channel_asset_id,
            external_user_id=external_user_id,
            display_name=display_name,
            last_seen_at=last_seen_at or datetime.now(UTC),
            identity_metadata=metadata or {},
        )
        session.add(identity)
    else:
        identity.contact_id = contact_id
        identity.display_name = display_name
        identity.last_seen_at = last_seen_at or datetime.now(UTC)
        if metadata is not None:
            identity.identity_metadata = metadata
    await session.flush()
    return identity
