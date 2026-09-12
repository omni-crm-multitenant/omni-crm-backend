from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.attribution import Attribution


router = APIRouter(prefix="/attributions", tags=["attributions"])


class AttributionResponse(BaseModel):
    id: UUID
    contact_id: UUID
    campaign_id: UUID | None
    ad_set_id: UUID | None
    ad_id: UUID | None
    source: str
    confidence: str
    raw_metadata: dict


@router.get("", response_model=list[AttributionResponse])
async def list_attributions(
    contact_id: UUID | None = None,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[AttributionResponse]:
    query = select(Attribution).where(Attribution.tenant_id == context.tenant_id)
    if contact_id is not None:
        query = query.where(Attribution.contact_id == contact_id)
    rows = list((await session.scalars(query.order_by(Attribution.created_at.desc(), Attribution.id.desc()))).all())
    return [AttributionResponse.model_validate(row, from_attributes=True) for row in rows]
