from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.tenant_context import TenantContext
from app.models.automation_action_attempt import AutomationActionAttempt
from app.models.automation_execution import AutomationExecution
from app.services.audit import write_audit_event
from app.api.dependencies import require_roles


router = APIRouter(prefix="/automation-executions", tags=["automation-executions"])


class ActionAttemptResponse(BaseModel):
    id: UUID
    action_index: int
    status: str
    result: dict
    created_at: datetime


class ExecutionResponse(BaseModel):
    id: UUID
    rule_id: UUID
    event_id: UUID
    status: str
    attempts: int
    result: dict
    started_at: datetime | None
    finished_at: datetime | None
    actions: list[ActionAttemptResponse]


async def _response(session: AsyncSession, execution: AutomationExecution) -> ExecutionResponse:
    actions = list((await session.scalars(select(AutomationActionAttempt).where(
        AutomationActionAttempt.tenant_id == execution.tenant_id,
        AutomationActionAttempt.execution_id == execution.id,
    ).order_by(AutomationActionAttempt.action_index))).all())
    return ExecutionResponse(
        id=execution.id, rule_id=execution.rule_id, event_id=execution.event_id,
        status=execution.status, attempts=execution.attempts, result=execution.result or {},
        started_at=execution.started_at, finished_at=execution.finished_at,
        actions=[ActionAttemptResponse.model_validate(action, from_attributes=True) for action in actions],
    )


@router.get("", response_model=list[ExecutionResponse])
async def list_executions(
    context: TenantContext = Depends(require_roles("administrador", "supervisor", "agente_comercial")),
    session: AsyncSession = Depends(get_session),
) -> list[ExecutionResponse]:
    rows = list((await session.scalars(select(AutomationExecution).where(
        AutomationExecution.tenant_id == context.tenant_id,
    ).order_by(AutomationExecution.started_at.desc().nullslast(), AutomationExecution.id.desc()))).all())
    return [await _response(session, row) for row in rows]


@router.post("/{execution_id}/redrive", response_model=ExecutionResponse)
async def redrive_execution(
    execution_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> ExecutionResponse:
    execution = await session.scalar(select(AutomationExecution).where(
        AutomationExecution.id == execution_id, AutomationExecution.tenant_id == context.tenant_id,
    ).with_for_update())
    if execution is None:
        raise HTTPException(status_code=404, detail={"code": "AUTOMATION_EXECUTION_NOT_FOUND"})
    if execution.status not in {"failed", "dead_letter"}:
        raise HTTPException(status_code=409, detail={"code": "EXECUTION_NOT_SAFE_TO_REDRIVE"})
    unknown = await session.scalar(select(AutomationActionAttempt.id).where(
        AutomationActionAttempt.tenant_id == context.tenant_id,
        AutomationActionAttempt.execution_id == execution.id,
        AutomationActionAttempt.status == "unknown",
    ).limit(1))
    if unknown is not None:
        raise HTTPException(status_code=409, detail={"code": "UNKNOWN_ACTION_CANNOT_REDRIVE"})
    execution.status = "received"
    execution.next_attempt_at = datetime.now(UTC)
    execution.lease_token = None
    execution.lease_expires_at = None
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="automation_execution.redriven", resource_type="automation_execution", resource_id=execution.id,
        metadata={"reason": "administrator_redrive"},
    )
    await session.flush()
    return await _response(session, execution)
