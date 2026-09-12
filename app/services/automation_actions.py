from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.crm import Message
from app.services.message_authors import MessageAuthor
from app.services.outbound_policy import OutboundPolicyError
from app.services.send_intent import send_outbound_message


async def execute_automation_send(
    session: AsyncSession,
    *,
    execution: AutomationExecution,
    conversation_id: UUID,
    body_text: str,
    action_id: UUID,
    purpose: str = "marketing",
) -> Message | None:
    """Execute one rule send and persist a visible policy block."""
    try:
        message = await send_outbound_message(
            session,
            tenant_id=execution.tenant_id,
            conversation_id=conversation_id,
            body_text=body_text,
            author=MessageAuthor.automation(action_id),
            purpose=purpose,
            idempotency_key=str(action_id),
        )
    except OutboundPolicyError as exc:
        execution.status = "blocked"
        execution.result = {
            **execution.result,
            "blocked": True,
            "code": exc.code,
            "action_id": str(action_id),
        }
        await session.flush()
        return None
    return message
