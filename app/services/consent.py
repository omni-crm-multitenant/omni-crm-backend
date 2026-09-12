from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Consent


async def has_active_consent(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    channel: str,
    purpose: str,
) -> bool:
    """Return the newest consent status for this exact contact scope."""
    latest = await session.scalar(select(Consent.status).where(
        Consent.tenant_id == tenant_id,
        Consent.contact_id == contact_id,
        Consent.channel == channel,
        Consent.purpose == purpose,
    ).order_by(desc(Consent.captured_at), desc(Consent.id)).limit(1))
    return latest == "granted"
