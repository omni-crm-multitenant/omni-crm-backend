from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.identity import ChannelAsset
from app.services.credentials import CredentialStore, get_credential_store
from app.services.meta_oauth import MetaGraphClient


class MetaMarketingClient:
    """Read-only adapter for Marketing API collection and insights endpoints."""

    def __init__(self, graph: MetaGraphClient | None = None) -> None:
        self.graph = graph or MetaGraphClient(get_settings())

    async def list_campaigns(self, ad_account_id: str, access_token: str) -> dict[str, Any]:
        return await self.graph.get(f"/{ad_account_id}/campaigns", access_token=access_token, params={"fields": "id,name,status,objective"})

    async def list_ad_sets(self, campaign_id: str, access_token: str) -> dict[str, Any]:
        return await self.graph.get(f"/{campaign_id}/adsets", access_token=access_token, params={"fields": "id,name,status"})

    async def list_ads(self, ad_set_id: str, access_token: str) -> dict[str, Any]:
        return await self.graph.get(f"/{ad_set_id}/ads", access_token=access_token, params={"fields": "id,name,status"})

    async def get_insights(
        self,
        object_id: str,
        access_token: str,
        *,
        fields: str = "impressions,reach,clicks,spend",
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self.graph.get(
            f"/{object_id}/insights",
            access_token=access_token,
            params={"fields": fields, **(params or {})},
        )

    async def list_campaigns_for_asset(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        asset_id: UUID,
        credential_store: CredentialStore | None = None,
    ) -> dict[str, Any]:
        asset = await session.scalar(
            select(ChannelAsset).where(
                ChannelAsset.id == asset_id,
                ChannelAsset.tenant_id == tenant_id,
                ChannelAsset.channel == "ad_account",
            )
        )
        if asset is None:
            raise LookupError("AD_ACCOUNT_ASSET_NOT_FOUND")
        token = await (credential_store or get_credential_store()).get(asset.credential_ref)
        return await self.list_campaigns(asset.external_id, token)
