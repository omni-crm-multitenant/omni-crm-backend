from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.marketing import Campaign
from app.api.dependencies import require_roles
from app.workers.campaign_tasks import sync_tenant_campaigns
from app.services.jobs import create_job


router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignResponse(BaseModel):
    id: UUID
    ad_account_channel_asset_id: UUID
    external_id: str
    name: str
    status: str
    objective: str
    metrics_snapshot: dict
    last_synced_at: object | None
    last_sync_error: str | None


class SyncResponse(BaseModel):
    job_id: str
    status: str


@router.post("/sync", response_model=SyncResponse, status_code=status.HTTP_202_ACCEPTED)
async def sync_campaigns_endpoint(
    response: Response,
    context: TenantContext = Depends(require_roles("administrador", "supervisor")),
    session: AsyncSession = Depends(get_session),
) -> SyncResponse:
    job_id = await create_job(session, context.tenant_id, "campaign_sync")
    sync_tenant_campaigns.delay(str(context.tenant_id), str(job_id))
    response.headers["Location"] = f"/api/v1/jobs/{job_id}"
    return SyncResponse(job_id=str(job_id), status="queued")


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[CampaignResponse]:
    campaigns = list((await session.scalars(
        select(Campaign).where(Campaign.tenant_id == context.tenant_id).order_by(Campaign.name.asc(), Campaign.id.asc())
    )).all())
    return [CampaignResponse.model_validate(item, from_attributes=True) for item in campaigns]
