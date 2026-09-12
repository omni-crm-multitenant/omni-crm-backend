from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunities import Opportunity
from app.models.pipeline import PipelineStage
from app.services.audit import write_audit_event
from app.services.custom_fields import validate_custom_field_payload


class OpportunityTransitionError(ValueError):
    pass


async def change_opportunity_stage(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    opportunity_id: UUID,
    target_stage_id: UUID,
    actor_user_id: UUID | None = None,
    actor_type: str | None = None,
) -> Opportunity:
    opportunity = await session.scalar(select(Opportunity).where(
        Opportunity.id == opportunity_id, Opportunity.tenant_id == tenant_id,
    ).with_for_update())
    if opportunity is None:
        raise LookupError("OPPORTUNITY_NOT_FOUND")
    stage = await session.scalar(select(PipelineStage).where(
        PipelineStage.id == target_stage_id,
        PipelineStage.tenant_id == tenant_id,
        PipelineStage.pipeline_id == opportunity.pipeline_id,
    ))
    if stage is None:
        raise OpportunityTransitionError("STAGE_NOT_IN_PIPELINE")
    if stage.terminal_type == "lost" and not opportunity.loss_reason:
        raise OpportunityTransitionError("LOSS_REASON_REQUIRED")
    previous_stage_id = opportunity.stage_id
    opportunity.stage_id = stage.id
    await write_audit_event(
        session, tenant_id=tenant_id, actor_type=actor_type or ("user" if actor_user_id else "system"),
        actor_user_id=actor_user_id, action="opportunity.stage_changed", resource_type="opportunity",
        resource_id=opportunity.id, metadata={"from_stage_id": previous_stage_id, "to_stage_id": stage.id},
    )
    await session.flush()
    return opportunity


async def validate_opportunity_custom_fields(
    session: AsyncSession, *, tenant_id: UUID, values: dict[str, Any]
) -> None:
    await validate_custom_field_payload(
        session, tenant_id=tenant_id, entity_type="opportunity", values=values, require_all=True
    )
