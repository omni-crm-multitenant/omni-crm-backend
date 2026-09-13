import asyncio
from uuid import UUID

from app.db.session import SessionFactory
from app.services.campaign_sync import sync_all_campaigns
from app.services.campaign_sync import sync_campaigns
from app.services.jobs import run_job
from app.models.identity import ChannelAsset
from sqlalchemy import select
from app.workers.celery_app import celery_app


@celery_app.task(name="campaigns.reconcile")
def reconcile_campaigns() -> int:
    async def run() -> int:
        async with SessionFactory() as session:
            total = await sync_all_campaigns(session)
            await session.commit()
            return total

    return asyncio.run(run())


@celery_app.task(name="campaigns.reconcile_tenant")
def sync_tenant_campaigns(tenant_id: str, job_id: str | None = None) -> int:
    async def run() -> int:
        async with SessionFactory() as session:
            assets = list((await session.scalars(select(ChannelAsset.id).where(
                ChannelAsset.tenant_id == tenant_id,
                ChannelAsset.channel == "ad_account",
                ChannelAsset.status == "connected",
            ))).all())
            if job_id is None:
                total = 0
                for asset_id in assets:
                    total += await sync_campaigns(session, UUID(tenant_id))
                    break
            else:
                async with run_job(session, UUID(job_id)) as job:
                    total = 0
                    for asset_id in assets:
                        total += await sync_campaigns(session, UUID(tenant_id))
                        break
                    job.result = {"synced": total}
            await session.commit()
            return total

    return asyncio.run(run())
