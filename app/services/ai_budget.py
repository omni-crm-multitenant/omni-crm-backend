from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AiUsageLedger
from app.services.ai_limits import AiLimitExceeded, AiTurnLimits


async def reserve_token_budget(session: AsyncSession, *, tenant_id: UUID, estimated_tokens: int, limits: AiTurnLimits, at: datetime | None = None) -> AiUsageLedger:
    if estimated_tokens < 0:
        raise ValueError("INVALID_TOKEN_RESERVATION")
    month = (at or datetime.now(UTC)).date().replace(day=1)
    ledger = await session.scalar(select(AiUsageLedger).where(
        AiUsageLedger.tenant_id == tenant_id, AiUsageLedger.month == month,
    ).with_for_update())
    if ledger is None:
        ledger = AiUsageLedger(tenant_id=tenant_id, month=month)
        session.add(ledger)
        await session.flush()
    if ledger.consumed_tokens + ledger.reserved_tokens + estimated_tokens > limits.monthly_token_budget:
        raise AiLimitExceeded("MONTHLY_TOKEN_BUDGET_EXCEEDED")
    ledger.reserved_tokens += estimated_tokens
    await session.flush()
    return ledger


async def settle_token_budget(session: AsyncSession, *, ledger: AiUsageLedger, reserved_tokens: int, actual_tokens: int) -> AiUsageLedger:
    ledger.reserved_tokens = max(0, ledger.reserved_tokens - reserved_tokens)
    ledger.consumed_tokens += max(0, actual_tokens)
    await session.flush()
    return ledger
