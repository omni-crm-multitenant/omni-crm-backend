from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.automation import AutomationRule
from app.services.audit import write_audit_event
from app.services.authorization import require_roles
from app.services.automation_rules import InvalidAutomationRule, validate_automation_rule


router = APIRouter(prefix="/automation-rules", tags=["automation-rules"])


class AutomationRuleInput(BaseModel):
    trigger_type: str
    conditions: dict = Field(default_factory=dict)
    actions: list[dict] = Field(default_factory=list)
    priority: int = 100
    enabled: bool = True
    duration_seconds: int | None = None
    clock: str | None = None


class AutomationRuleResponse(AutomationRuleInput):
    id: UUID
    tenant_id: UUID
    version: int
    created_at: datetime


def _validate(payload: AutomationRuleInput) -> None:
    try:
        validate_automation_rule(
            trigger_type=payload.trigger_type, conditions=payload.conditions,
            actions=payload.actions, duration_seconds=payload.duration_seconds, clock=payload.clock,
        )
    except InvalidAutomationRule as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_AUTOMATION_RULE", "reason": str(exc)}) from exc


@router.post("", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AutomationRuleInput,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> AutomationRuleResponse:
    _validate(payload)
    rule = AutomationRule(tenant_id=context.tenant_id, **payload.model_dump())
    session.add(rule)
    await session.flush()
    await write_audit_event(session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id, action="automation_rule.created", resource_type="automation_rule", resource_id=rule.id)
    return AutomationRuleResponse.model_validate(rule, from_attributes=True)


@router.get("", response_model=list[AutomationRuleResponse])
async def list_rules(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[AutomationRuleResponse]:
    rows = list((await session.scalars(select(AutomationRule).where(AutomationRule.tenant_id == context.tenant_id).order_by(AutomationRule.priority, AutomationRule.id))).all())
    return [AutomationRuleResponse.model_validate(row, from_attributes=True) for row in rows]


@router.patch("/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(
    rule_id: UUID,
    payload: AutomationRuleInput,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> AutomationRuleResponse:
    _validate(payload)
    rule = await session.scalar(select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.tenant_id == context.tenant_id).with_for_update())
    if rule is None:
        raise HTTPException(status_code=404, detail={"code": "AUTOMATION_RULE_NOT_FOUND"})
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    rule.version += 1
    await write_audit_event(session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id, action="automation_rule.updated", resource_type="automation_rule", resource_id=rule.id, metadata={"version": rule.version})
    await session.flush()
    return AutomationRuleResponse.model_validate(rule, from_attributes=True)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_rule(
    rule_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await session.scalar(select(AutomationRule).where(AutomationRule.id == rule_id, AutomationRule.tenant_id == context.tenant_id).with_for_update())
    if rule is None:
        raise HTTPException(status_code=404, detail={"code": "AUTOMATION_RULE_NOT_FOUND"})
    await write_audit_event(session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id, action="automation_rule.deleted", resource_type="automation_rule", resource_id=rule.id)
    await session.delete(rule)
