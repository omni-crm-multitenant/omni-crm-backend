from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Conversation
from app.models.opportunities import Opportunity
from app.models.pipeline import PipelineStage
from app.services.audit import write_audit_event
from app.services.handoff import TRANSFER_REASONS, handoff
from app.services.opportunity_stages import change_opportunity_stage


CONTACT_CONTEXT_FIELDS = frozenset({
    "id", "name", "phone", "email", "source_channel", "source_campaign_id", "owner_user_id", "status", "tags", "custom_fields",
})
OPPORTUNITY_CONTEXT_FIELDS = frozenset({
    "id", "contact_id", "pipeline_id", "stage_id", "owner_user_id", "amount", "currency", "loss_reason", "expected_close_at", "custom_fields",
})


def _tool_decorator(function):
    function.name = function.__name__
    function.description = function.__doc__ or ""
    return function


def build_change_stage_tool(session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID):
    @_tool_decorator
    async def change_stage(new_stage_name: str) -> dict:
        """Change the current opportunity stage only when AI policy allows it."""
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ))
        if conversation is None:
            raise LookupError("CONVERSATION_NOT_FOUND")
        opportunity = await session.scalar(select(Opportunity).where(
            Opportunity.tenant_id == tenant_id, Opportunity.contact_id == conversation.contact_id,
        ).order_by(Opportunity.created_at.desc()).limit(1).with_for_update())
        if opportunity is None:
            raise LookupError("OPPORTUNITY_NOT_FOUND")
        stage = await session.scalar(select(PipelineStage).where(
            PipelineStage.tenant_id == tenant_id, PipelineStage.pipeline_id == opportunity.pipeline_id,
            PipelineStage.name == new_stage_name,
        ))
        if stage is None:
            raise ValueError("STAGE_NOT_FOUND")
        if not stage.ai_can_transition:
            raise ValueError("AI_STAGE_TRANSITION_REQUIRES_HUMAN")
        updated = await change_opportunity_stage(
            session, tenant_id=tenant_id, opportunity_id=opportunity.id,
            target_stage_id=stage.id, actor_type="ai",
        )
        return {"opportunity_id": str(updated.id), "stage_id": str(updated.stage_id)}

    return change_stage


def build_create_followup_task_tool(
    session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, ai_run_id: UUID,
):
    @_tool_decorator
    async def create_followup_task(title: str, due_at: datetime, notes: str | None = None) -> dict:
        """Create a future AI follow-up linked to this conversation."""
        if due_at <= datetime.now(UTC):
            raise ValueError("DUE_AT_MUST_BE_FUTURE")
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ))
        if conversation is None:
            raise LookupError("CONVERSATION_NOT_FOUND")
        from app.models.tasks import Task
        opportunity = await session.scalar(select(Opportunity).where(
            Opportunity.tenant_id == tenant_id, Opportunity.contact_id == conversation.contact_id,
        ).order_by(Opportunity.created_at.desc()).limit(1))
        task = Task(
            tenant_id=tenant_id, title=title, description=notes, due_at=due_at,
            source="ai", source_ref_id=ai_run_id, contact_id=conversation.contact_id,
            conversation_id=conversation.id, opportunity_id=opportunity.id if opportunity else None,
        )
        session.add(task)
        await write_audit_event(
            session, tenant_id=tenant_id, actor_type="ai", action="task.created",
            resource_type="task", resource_id=task.id,
            metadata={"ai_run_id": str(ai_run_id), "source": "ai"},
        )
        await session.flush()
        return {"task_id": str(task.id), "conversation_id": str(conversation.id)}

    return create_followup_task


def build_request_human_transfer_tool(
    session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, trigger_id: UUID,
):
    allowed_reasons = TRANSFER_REASONS

    @_tool_decorator
    async def request_human_transfer(reason: str) -> dict:
        """Request a durable human handoff without trusting model-selected IDs."""
        if reason not in allowed_reasons:
            raise ValueError("INVALID_HANDOFF_REASON")
        transfer = await handoff(
            session, tenant_id=tenant_id, conversation_id=conversation_id,
            trigger_id=trigger_id, reason=reason, actor_type="ai",
        )
        return {"transfer_id": str(transfer.id), "status": transfer.status}

    return request_human_transfer
