from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.api.dependencies import require_roles
from app.services.authorization import validate_assignee_membership


router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class OpportunityCreate(BaseModel):
    contact_id: UUID
    pipeline_id: UUID
    stage_id: UUID
    owner_user_id: UUID | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    loss_reason: str | None = None
    expected_close_at: datetime | None = None
    custom_fields: dict = Field(default_factory=dict)


class OpportunityResponse(OpportunityCreate):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime


class StageChangeRequest(BaseModel):
    new_stage_id: UUID
    loss_reason: str | None = None


class AssignmentRequest(BaseModel):
    owner_user_id: UUID


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    payload: OpportunityCreate,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    from app.models.opportunities import Opportunity
    from app.services.opportunities import validate_opportunity_values

    await validate_opportunity_values(session, tenant_id=context.tenant_id, custom_fields=payload.custom_fields)
    values = payload.model_dump()
    if values.get("owner_user_id") is None:
        from app.services.round_robin import next_round_robin_agent
        values["owner_user_id"] = await next_round_robin_agent(session, context.tenant_id)
    opportunity = Opportunity(tenant_id=context.tenant_id, **values)
    session.add(opportunity)
    try:
        await session.flush()
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_OPPORTUNITY_REFERENCE"}) from exc
    return OpportunityResponse.model_validate(opportunity, from_attributes=True)


@router.get("", response_model=list[OpportunityResponse])
async def list_opportunities(
    stage_id: UUID | None = Query(default=None),
    owner_user_id: UUID | None = Query(default=None),
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[OpportunityResponse]:
    from app.models.opportunities import Opportunity

    query = select(Opportunity).where(Opportunity.tenant_id == context.tenant_id)
    if stage_id is not None:
        query = query.where(Opportunity.stage_id == stage_id)
    if owner_user_id is not None:
        query = query.where(Opportunity.owner_user_id == owner_user_id)
    rows = list((await session.scalars(query.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()))).all())
    return [OpportunityResponse.model_validate(item, from_attributes=True) for item in rows]


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    from app.models.opportunities import Opportunity

    opportunity = await session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.tenant_id == context.tenant_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail={"code": "OPPORTUNITY_NOT_FOUND"})
    return OpportunityResponse.model_validate(opportunity, from_attributes=True)


@router.patch("/{opportunity_id}/stage", response_model=OpportunityResponse)
async def change_stage(
    opportunity_id: UUID,
    payload: StageChangeRequest,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    from app.services.opportunity_stages import OpportunityTransitionError, change_opportunity_stage
    from app.models.opportunities import Opportunity

    opportunity = await session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.tenant_id == context.tenant_id))
    if opportunity is None:
        raise HTTPException(status_code=404, detail={"code": "OPPORTUNITY_NOT_FOUND"})
    if payload.loss_reason is not None:
        opportunity.loss_reason = payload.loss_reason
    try:
        updated = await change_opportunity_stage(
            session, tenant_id=context.tenant_id, opportunity_id=opportunity_id,
            target_stage_id=payload.new_stage_id, actor_user_id=context.user_id,
        )
    except OpportunityTransitionError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc
    return OpportunityResponse.model_validate(updated, from_attributes=True)


@router.patch("/{opportunity_id}/assignment", response_model=OpportunityResponse)
async def assign_opportunity(
    opportunity_id: UUID,
    payload: AssignmentRequest,
    context: TenantContext = Depends(require_roles("supervisor", "administrador")),
    session: AsyncSession = Depends(get_session),
) -> OpportunityResponse:
    from app.models.opportunities import Opportunity
    from app.services.audit import write_audit_event

    opportunity = await session.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.tenant_id == context.tenant_id).with_for_update())
    if opportunity is None:
        raise HTTPException(status_code=404, detail={"code": "OPPORTUNITY_NOT_FOUND"})
    try:
        target_membership = await validate_assignee_membership(session, context, payload.owner_user_id)
        if target_membership.role not in {"agente_comercial", "supervisor"}:
            raise ValueError("INVALID_ASSIGNEE")
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_ASSIGNEE"}) from exc
    previous_owner_user_id = opportunity.owner_user_id
    opportunity.owner_user_id = payload.owner_user_id
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="opportunity.assigned", resource_type="opportunity", resource_id=opportunity.id,
        metadata={"previous_owner_user_id": previous_owner_user_id, "new_owner_user_id": payload.owner_user_id},
    )
    await session.flush()
    return OpportunityResponse.model_validate(opportunity, from_attributes=True)
