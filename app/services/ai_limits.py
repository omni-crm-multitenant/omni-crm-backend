from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Integer, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import TenantSettings


@dataclass(frozen=True)
class AiTurnLimits:
    max_output_tokens: int = 512
    timeout_seconds: int = 30
    max_tool_calls: int = 8
    max_retries: int = 2
    monthly_token_budget: int = 100000


class AiLimitExceeded(RuntimeError):
    pass


async def load_ai_limits(session: AsyncSession, tenant_id: UUID) -> AiTurnLimits:
    settings = await session.get(TenantSettings, tenant_id)
    if settings is None:
        return AiTurnLimits()
    return AiTurnLimits(
        max_output_tokens=settings.max_output_tokens, timeout_seconds=settings.timeout_seconds,
        max_tool_calls=settings.max_tool_calls, max_retries=settings.max_retries,
        monthly_token_budget=settings.monthly_token_budget,
    )


async def invoke_with_limits(operation, *, limits: AiTurnLimits, tool_call_count: int = 0):
    if tool_call_count > limits.max_tool_calls:
        raise AiLimitExceeded("TOOL_CALL_LIMIT_EXCEEDED")
    for attempt in range(limits.max_retries + 1):
        try:
            result = await asyncio.wait_for(operation(), timeout=limits.timeout_seconds)
            if isinstance(result, str) and len(result) > limits.max_output_tokens * 4:
                raise AiLimitExceeded("OUTPUT_LENGTH_EXCEEDED")
            return result
        except AiLimitExceeded:
            raise
        except Exception:
            if attempt >= limits.max_retries:
                raise AiLimitExceeded("AI_RETRY_LIMIT_EXCEEDED")
    raise AiLimitExceeded("AI_RETRY_LIMIT_EXCEEDED")
