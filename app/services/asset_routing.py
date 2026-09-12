from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import ChannelAsset


@dataclass(frozen=True)
class AssetRoutingResult:
    status: Literal["resolved", "quarantined"]
    reason: Literal["unknown_asset", "ambiguous_asset"] | None = None
    tenant_id: UUID | None = None
    asset_id: UUID | None = None


async def resolve_inbound_asset(
    session: AsyncSession,
    *,
    meta_app_id: str,
    channel: str,
    recipient_external_id: str,
) -> AssetRoutingResult:
    assets = list(
        await session.scalars(
            select(ChannelAsset).where(
                ChannelAsset.meta_app_id == meta_app_id,
                ChannelAsset.channel == channel,
                ChannelAsset.external_id == recipient_external_id,
                ChannelAsset.status == "connected",
            ).limit(2)
        )
    )
    if not assets:
        return AssetRoutingResult(status="quarantined", reason="unknown_asset")
    if len(assets) != 1:
        return AssetRoutingResult(status="quarantined", reason="ambiguous_asset")
    asset = assets[0]
    return AssetRoutingResult(status="resolved", tenant_id=asset.tenant_id, asset_id=asset.id)
