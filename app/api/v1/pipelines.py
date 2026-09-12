from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.pipeline import Pipeline, PipelineStage
from app.services.audit import write_audit_event
from app.services.authorization import require_roles


router = APIRouter(prefix="/pipelines", tags=["pipelines"])


class PipelineResponse(BaseModel):
    id: UUID
    name: str
    is_default: bool


class StageResponse(BaseModel):
    id: UUID
    pipeline_id: UUID
    name: str
    position: int
    terminal_type: str
    ai_can_transition: bool


class StagePolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ai_can_transition: bool


@router.get("", response_model=list[PipelineResponse])
async def list_pipelines(context: TenantContext = Depends(require_tenant_context), session: AsyncSession = Depends(get_session)) -> list[PipelineResponse]:
    rows = list((await session.scalars(select(Pipeline).where(Pipeline.tenant_id == context.tenant_id).order_by(Pipeline.is_default.desc(), Pipeline.id))).all())
    return [PipelineResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/{pipeline_id}/stages", response_model=list[StageResponse])
async def list_stages(pipeline_id: UUID, context: TenantContext = Depends(require_tenant_context), session: AsyncSession = Depends(get_session)) -> list[StageResponse]:
    pipeline = await session.scalar(select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.tenant_id == context.tenant_id))
    if pipeline is None:
        raise HTTPException(status_code=404, detail={"code": "PIPELINE_NOT_FOUND"})
    rows = list((await session.scalars(select(PipelineStage).where(PipelineStage.pipeline_id == pipeline_id, PipelineStage.tenant_id == context.tenant_id).order_by(PipelineStage.position))).all())
    return [StageResponse.model_validate(row, from_attributes=True) for row in rows]


@router.patch("/stages/{stage_id}", response_model=StageResponse)
async def update_stage_policy(stage_id: UUID, payload: StagePolicyUpdate, context: TenantContext = Depends(require_roles("administrador")), session: AsyncSession = Depends(get_session)) -> StageResponse:
    stage = await session.scalar(select(PipelineStage).where(PipelineStage.id == stage_id, PipelineStage.tenant_id == context.tenant_id).with_for_update())
    if stage is None:
        raise HTTPException(status_code=404, detail={"code": "STAGE_NOT_FOUND"})
    stage.ai_can_transition = payload.ai_can_transition
    await write_audit_event(session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id, action="pipeline_stage.ai_policy_changed", resource_type="pipeline_stage", resource_id=stage.id, metadata={"ai_can_transition": stage.ai_can_transition})
    await session.flush()
    return StageResponse.model_validate(stage, from_attributes=True)


@router.delete("/stages/{stage_id}", status_code=422, response_model=None)
async def reject_stage_delete(stage_id: UUID, context: TenantContext = Depends(require_roles("administrador"))) -> None:
    raise HTTPException(status_code=422, detail={"code": "STANDARD_PIPELINE_FIXED"})
