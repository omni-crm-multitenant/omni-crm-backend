from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.identity import ChannelAsset
from app.services.credentials import CredentialNotFound, CredentialStore, get_credential_store
from app.services.meta_oauth import MetaGraphClient, MetaOAuthError, MetaOAuthNotConfigured


async def revalidate_channel_asset(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    asset_id: UUID,
    credential_store: CredentialStore | None = None,
) -> ChannelAsset | None:
    asset = await session.scalar(
        select(ChannelAsset)
        .where(ChannelAsset.id == asset_id, ChannelAsset.tenant_id == tenant_id)
        .with_for_update()
    )
    if asset is None:
        return None
    store = credential_store or get_credential_store()
    try:
        token = await store.get(asset.credential_ref)
        payload = await MetaGraphClient(get_settings()).debug_token(token)
        data = payload.get("data", {})
        if not isinstance(data, dict) or data.get("is_valid") is not True:
            asset.status = "expired"
        else:
            asset.status = "connected"
            expires_at = data.get("expires_at")
            if isinstance(expires_at, (int, float)) and expires_at > 0:
                asset.credential_expires_at = datetime.fromtimestamp(expires_at, tz=UTC)
    except (CredentialNotFound, MetaOAuthError, MetaOAuthNotConfigured):
        asset.status = "error"
    await session.flush()
    return asset
