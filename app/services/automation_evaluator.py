from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationRule
from app.services.domain_events import DomainEvent


@dataclass(frozen=True)
class ActionPlan:
    rule_id: UUID
    rule_version: int
    actions: list[dict[str, Any]]


def _matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    field = condition.get("field")
    value = context.get(field) if isinstance(field, str) else None
    expected = condition.get("value")
    operator = condition.get("operator")
    if operator == "eq":
        return value == expected
    if operator == "neq":
        return value != expected
    if operator == "in":
        return value in (expected or [])
    if operator == "contains":
        return expected in (value or [])
    if operator == "exists":
        return (value is not None) == bool(expected)
    return False


async def evaluate_domain_event(
    session: AsyncSession, event: DomainEvent
) -> list[ActionPlan]:
    rules = list(
        (
            await session.scalars(
                select(AutomationRule)
                .where(
                    AutomationRule.tenant_id == event.tenant_id,
                    AutomationRule.enabled.is_(True),
                    AutomationRule.trigger_type == event.type,
                )
                .order_by(AutomationRule.priority, AutomationRule.id)
            )
        ).all()
    )
    plans = []
    for rule in rules:
        conditions = (
            rule.conditions.get("all", []) if isinstance(rule.conditions, dict) else []
        )
        if all(_matches(condition, event.payload) for condition in conditions):
            plans.append(
                ActionPlan(
                    rule_id=rule.id,
                    rule_version=rule.version,
                    actions=list(rule.actions),
                )
            )
    return plans
