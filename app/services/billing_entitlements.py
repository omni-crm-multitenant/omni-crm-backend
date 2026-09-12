from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingPlan, Subscription
from app.services.billing_usage import usage_meters


class EntitlementExceeded(PermissionError):
    code = "BILLING_ENTITLEMENT_EXCEEDED"


async def assert_entitlement(session: AsyncSession, *, tenant_id: UUID, meter: str, quantity: int = 1) -> None:
    subscription = await session.scalar(select(Subscription).where(
        Subscription.tenant_id == tenant_id,
        Subscription.status.in_(("trialing", "active", "past_due")),
    ))
    if subscription is None:
        raise EntitlementExceeded("BILLING_SUBSCRIPTION_REQUIRED")
    plan = await session.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise EntitlementExceeded("BILLING_PLAN_MISSING")
    limit = {"contacts": plan.contact_limit, "conversations": plan.conversation_limit, "connected_assets": plan.asset_limit}.get(meter)
    if limit is None:
        raise ValueError("UNKNOWN_BILLING_METER")
    current = (await usage_meters(session, tenant_id=tenant_id)).get(meter, 0)
    if current + quantity > limit:
        raise EntitlementExceeded()
