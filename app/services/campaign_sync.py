from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import ChannelAsset
from app.models.marketing import Ad, AdSet, Campaign
from app.services.credentials import CredentialStore, get_credential_store
from app.services.meta_marketing import MetaMarketingClient


async def _sync_children(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    campaign_id: UUID,
    ad_set_rows: list[dict[str, Any]],
    marketing: MetaMarketingClient,
    token: str,
) -> None:
    for row in ad_set_rows:
        external_id = str(row.get("id") or "")
        if not external_id:
            continue
        ad_set = await session.scalar(
            select(AdSet).where(
                AdSet.tenant_id == tenant_id,
                AdSet.campaign_id == campaign_id,
                AdSet.external_id == external_id,
            )
        )
        if ad_set is None:
            ad_set = AdSet(tenant_id=tenant_id, campaign_id=campaign_id, external_id=external_id, name=str(row.get("name") or external_id))
            session.add(ad_set)
            await session.flush()
        else:
            ad_set.name = str(row.get("name") or ad_set.name)
        ads_payload = await marketing.list_ads(external_id, token)
        for ad_row in ads_payload.get("data", []):
            ad_external_id = str(ad_row.get("id") or "")
            if not ad_external_id:
                continue
            ad = await session.scalar(
                select(Ad).where(
                    Ad.tenant_id == tenant_id,
                    Ad.ad_set_id == ad_set.id,
                    Ad.external_id == ad_external_id,
                )
            )
            if ad is None:
                session.add(Ad(tenant_id=tenant_id, ad_set_id=ad_set.id, external_id=ad_external_id, name=str(ad_row.get("name") or ad_external_id)))
            else:
                ad.name = str(ad_row.get("name") or ad.name)


async def sync_campaigns(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    marketing: MetaMarketingClient | None = None,
    credential_store: CredentialStore | None = None,
) -> int:
    marketing = marketing or MetaMarketingClient()
    store = credential_store or get_credential_store()
    assets = list(
        (
            await session.scalars(
                select(ChannelAsset).where(
                    ChannelAsset.tenant_id == tenant_id,
                    ChannelAsset.channel == "ad_account",
                    ChannelAsset.status == "connected",
                )
            )
        ).all()
    )
    synced = 0
    for asset in assets:
        try:
            token = await store.get(asset.credential_ref)
            payload = await marketing.list_campaigns(asset.external_id, token)
            for row in payload.get("data", []):
                external_id = str(row.get("id") or "")
                if not external_id:
                    continue
                campaign = await session.scalar(
                    select(Campaign).where(Campaign.tenant_id == tenant_id, Campaign.external_id == external_id)
                )
                if campaign is None:
                    campaign = Campaign(
                        tenant_id=tenant_id,
                        ad_account_channel_asset_id=asset.id,
                        external_id=external_id,
                        name=str(row.get("name") or external_id),
                        status=str(row.get("status") or "unknown"),
                        objective=str(row.get("objective") or "unknown"),
                        metrics_snapshot={},
                    )
                    session.add(campaign)
                    await session.flush()
                else:
                    campaign.ad_account_channel_asset_id = asset.id
                    campaign.name = str(row.get("name") or campaign.name)
                    campaign.status = str(row.get("status") or campaign.status)
                    campaign.objective = str(row.get("objective") or campaign.objective)
                ad_sets = await marketing.list_ad_sets(external_id, token)
                await _sync_children(
                    session,
                    tenant_id=tenant_id,
                    campaign_id=campaign.id,
                    ad_set_rows=list(ad_sets.get("data", [])),
                    marketing=marketing,
                    token=token,
                )
                campaign.last_synced_at = datetime.now(UTC)
                campaign.last_sync_error = None
                synced += 1
        except Exception as exc:
            existing = list(
                (
                    await session.scalars(
                        select(Campaign).where(
                            Campaign.tenant_id == tenant_id,
                            Campaign.ad_account_channel_asset_id == asset.id,
                        )
                    )
                ).all()
            )
            for campaign in existing:
                campaign.last_sync_error = type(exc).__name__
    await session.flush()
    return synced


async def sync_all_campaigns(session: AsyncSession) -> int:
    tenant_ids = list((await session.scalars(
        select(ChannelAsset.tenant_id).where(
            ChannelAsset.channel == "ad_account", ChannelAsset.status == "connected"
        ).distinct()
    )).all())
    total = 0
    for tenant_id in tenant_ids:
        total += await sync_campaigns(session, tenant_id)
    return total
