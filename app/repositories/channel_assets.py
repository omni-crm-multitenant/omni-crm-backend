from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import ChannelAsset
from app.services.credentials import CredentialStore

if TYPE_CHECKING:
    from app.services.meta_oauth import MetaAssetCandidate


async def upsert_meta_assets(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    meta_app_id: str,
    candidates: list[MetaAssetCandidate],
    credential_store: CredentialStore,
) -> list[ChannelAsset]:
    """Persist only assets returned by Meta; keep provider tokens outside the database."""
    persisted: list[ChannelAsset] = []
    for candidate in candidates:
        asset = await session.scalar(
            select(ChannelAsset)
            .where(
                ChannelAsset.tenant_id == tenant_id,
                ChannelAsset.channel == candidate.channel.value,
                ChannelAsset.external_id == candidate.external_id,
                ChannelAsset.meta_app_id == meta_app_id,
            )
            .with_for_update()
        )
        credential_ref = await credential_store.put(candidate.credential)
        if asset is None:
            asset = ChannelAsset(
                tenant_id=tenant_id,
                channel=candidate.channel.value,
                external_id=candidate.external_id,
                meta_app_id=meta_app_id,
                credential_ref=credential_ref,
                scopes=list(candidate.scopes),
                credential_expires_at=candidate.credential_expires_at,
                status="connected",
            )
            session.add(asset)
        else:
            old_credential_ref = asset.credential_ref
            asset.credential_ref = credential_ref
            asset.scopes = list(candidate.scopes)
            asset.credential_expires_at = candidate.credential_expires_at
            asset.status = "connected"
            if old_credential_ref != credential_ref:
                await credential_store.delete(old_credential_ref)
        persisted.append(asset)
    await session.flush()
    return persisted
