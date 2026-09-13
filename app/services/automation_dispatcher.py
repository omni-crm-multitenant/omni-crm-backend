from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationRule
from app.models.automation_execution import AutomationExecution
from app.models.crm import Contact, Conversation
from app.models.opportunities import Opportunity
from app.services.automation_actions import execute_automation_send
from app.services.automation_ledger import claim_action_attempt, finish_action_attempt
from app.services.opportunity_stages import change_opportunity_stage


@dataclass(frozen=True)
class ActionContext:
    tenant_id: UUID
    conversation_id: UUID
    contact_id: UUID
    opportunity_id: UUID | None = None


async def _handle_action(session: AsyncSession, *, action: dict[str, Any], context: ActionContext, execution: AutomationExecution, action_id: UUID) -> dict[str, Any]:
    action_type = action.get("type")
    if action_type == "send_message":
        message = await execute_automation_send(
            session, execution=execution, conversation_id=context.conversation_id,
            body_text=str(action.get("body", "")), action_id=action_id,
            purpose=str(action.get("purpose", "marketing")),
        )
        if message is None:
            raise PermissionError("CONSENT_REQUIRED")
        return {"message_id": str(message.id), "status": "queued"}
    if action_type in {"add_tag", "remove_tag"}:
        contact = await session.scalar(select(Contact).where(
            Contact.id == context.contact_id, Contact.tenant_id == context.tenant_id,
        ).with_for_update())
        if contact is None:
            raise LookupError("CONTACT_NOT_FOUND")
        tag = str(action.get("tag", "")).strip()
        if not tag:
            raise ValueError("TAG_REQUIRED")
        tags = list(contact.tags or [])
        if action_type == "add_tag" and tag not in tags:
            tags.append(tag)
        if action_type == "remove_tag":
            tags = [item for item in tags if item != tag]
        contact.tags = tags
        return {"contact_id": str(contact.id), "tags": tags}
    if action_type == "assign_agent":
        conversation = await session.scalar(select(Conversation).where(
            Conversation.id == context.conversation_id, Conversation.tenant_id == context.tenant_id,
        ).with_for_update())
        if conversation is None:
            raise LookupError("CONVERSATION_NOT_FOUND")
        target = action.get("user_id")
        if not target:
            raise ValueError("ASSIGNEE_REQUIRED")
        conversation.assigned_user_id = UUID(str(target))
        return {"conversation_id": str(conversation.id), "assigned_user_id": str(conversation.assigned_user_id)}
    if action_type == "change_stage":
        if context.opportunity_id is None:
            raise LookupError("OPPORTUNITY_NOT_FOUND")
        opportunity = await session.scalar(select(Opportunity).where(
            Opportunity.id == context.opportunity_id,
            Opportunity.tenant_id == context.tenant_id,
        ))
        if opportunity is None:
            raise LookupError("OPPORTUNITY_NOT_FOUND")
        updated = await change_opportunity_stage(
            session, tenant_id=context.tenant_id, opportunity_id=context.opportunity_id,
            target_stage_id=UUID(str(action["stage_id"])), actor_type="system",
        )
        return {"opportunity_id": str(updated.id), "stage_id": str(updated.stage_id)}
    if action_type == "create_task":
        from app.models.tasks import Task
        task = Task(
            tenant_id=context.tenant_id, title=str(action.get("title", "Seguimiento")),
            description=action.get("notes"), source="rule", source_ref_id=execution.rule_id,
            contact_id=context.contact_id, conversation_id=context.conversation_id,
            opportunity_id=context.opportunity_id, due_at=action.get("due_at"),
        )
        session.add(task)
        await session.flush()
        return {"task_id": str(task.id)}
    raise ValueError("UNKNOWN_ACTION")


async def execute_actions(
    session: AsyncSession, *, rule: AutomationRule, event_context: ActionContext,
    execution: AutomationExecution,
) -> list[dict[str, Any]]:
    results = []
    for index, action in enumerate(rule.actions or []):
        attempt = await claim_action_attempt(
            session, tenant_id=event_context.tenant_id, execution_id=execution.id,
            action_index=index, idempotency_key=f"{execution.id}:{index}",
        )
        if attempt is None:
            results.append({"action_index": index, "status": "processing"})
            continue
        if attempt.status == "succeeded":
            results.append({"action_index": index, "status": "succeeded", **attempt.result})
            continue
        try:
            result = await _handle_action(
                session, action=action, context=event_context,
                execution=execution, action_id=attempt.id,
            )
        except Exception as exc:
            status = "unknown" if isinstance(exc, TimeoutError) else "failed"
            await finish_action_attempt(session, attempt=attempt, lease_token=attempt.lease_token or "", status=status, result={"error": str(exc)})
            results.append({"action_index": index, "status": status, "error": str(exc)})
            if status == "unknown":
                break
        else:
            await finish_action_attempt(session, attempt=attempt, lease_token=attempt.lease_token or "", status="succeeded", result=result)
            results.append({"action_index": index, "status": "succeeded", **result})
    return results
