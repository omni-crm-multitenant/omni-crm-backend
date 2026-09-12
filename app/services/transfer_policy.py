from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.handoff import TRANSFER_REASONS, handoff


DEFAULT_CONFIDENCE_THRESHOLD = 0.6


def classify_transfer_trigger(
    *, explicit_request: bool = False, purchase_intent: bool = False,
    confidence: float | None = None, complex_request: bool = False,
    tool_failure: bool = False, limit_exceeded: bool = False,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> str | None:
    if explicit_request:
        return "explicit_request"
    if purchase_intent:
        return "purchase_intent"
    if confidence is not None and confidence < confidence_threshold:
        return "low_confidence"
    if complex_request:
        return "complex"
    if tool_failure:
        return "tool_failure"
    if limit_exceeded:
        return "limit_exceeded"
    return None


async def route_transfer_trigger(
    session: AsyncSession, *, tenant_id: UUID, conversation_id: UUID, trigger_id: UUID, reason: str,
):
    if reason not in TRANSFER_REASONS:
        raise ValueError("INVALID_TRANSFER_REASON")
    return await handoff(
        session, tenant_id=tenant_id, conversation_id=conversation_id,
        trigger_id=trigger_id, reason=reason, actor_type="ai",
    )
