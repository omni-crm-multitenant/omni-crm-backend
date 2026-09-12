from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingPlan, Subscription


async def activate_subscription(session: AsyncSession, *, tenant_id: UUID, plan_id: UUID, period_start: date, period_end: date) -> Subscription:
    subscription = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id).with_for_update())
    if subscription is None:
        subscription = Subscription(tenant_id=tenant_id, plan_id=plan_id, status="active", payment_period_start=period_start, payment_period_end=period_end, paid_through=period_end)
        session.add(subscription)
    else:
        subscription.plan_id = plan_id
        subscription.status = "active"
        subscription.payment_period_start = period_start
        subscription.payment_period_end = period_end
        subscription.paid_through = period_end
    await session.flush()
    return subscription


async def renew_subscription(session: AsyncSession, *, tenant_id: UUID, paid_through: date) -> Subscription:
    subscription = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id).with_for_update())
    if subscription is None:
        raise LookupError("SUBSCRIPTION_NOT_FOUND")
    if subscription.paid_through is not None and paid_through <= subscription.paid_through:
        return subscription
    subscription.payment_period_start = subscription.payment_period_end
    subscription.payment_period_end = paid_through
    subscription.paid_through = paid_through
    subscription.status = "active"
    await session.flush()
    return subscription


async def mark_payment_failed(session: AsyncSession, *, tenant_id: UUID, grace_days: int = 7) -> Subscription:
    subscription = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id).with_for_update())
    if subscription is None:
        raise LookupError("SUBSCRIPTION_NOT_FOUND")
    subscription.status = "past_due"
    if subscription.paid_through is None:
        subscription.paid_through = subscription.payment_period_end + timedelta(days=grace_days)
    await session.flush()
    return subscription


async def suspend_expired_subscriptions(session: AsyncSession, *, today: date | None = None) -> int:
    today = today or date.today()
    rows = list((await session.scalars(select(Subscription).where(
        Subscription.status == "past_due", Subscription.paid_through < today,
    ).with_for_update())).all())
    for subscription in rows:
        subscription.status = "suspended"
    await session.flush()
    return len(rows)


async def cancel_subscription(session: AsyncSession, *, tenant_id: UUID) -> Subscription:
    subscription = await session.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id).with_for_update())
    if subscription is None:
        raise LookupError("SUBSCRIPTION_NOT_FOUND")
    subscription.status = "cancelled"
    await session.flush()
    return subscription
