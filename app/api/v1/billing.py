from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.config import get_settings
from app.core.tenant_context import TenantContext
from app.models.billing import BillingPlan, Subscription
from app.api.dependencies import require_roles
from app.services.billing_lifecycle import cancel_subscription
from app.services.billing_provider import ProviderNotEnabled, billing_provider
from app.services.billing_usage import usage_meters


router = APIRouter(prefix="/billing", tags=["billing"])


class PlanResponse(BaseModel):
    code: str
    version: int
    currency: str
    amount_minor: int
    interval: str
    contact_limit: int
    conversation_limit: int
    asset_limit: int


class SubscriptionResponse(BaseModel):
    id: UUID
    plan_id: UUID
    status: str
    payment_period_start: date
    payment_period_end: date
    paid_through: date | None


class CheckoutRequest(BaseModel):
    plan_code: str


class CheckoutResponse(BaseModel):
    reference: str
    url: str


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    _context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[PlanResponse]:
    rows = list((await session.scalars(select(BillingPlan).where(BillingPlan.enabled.is_(True)).order_by(BillingPlan.code, BillingPlan.version.desc()))).all())
    return [PlanResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def current_subscription(
    context: TenantContext = Depends(require_roles("administrador", "supervisor", "agente_comercial")),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse | None:
    row = await session.scalar(select(Subscription).where(Subscription.tenant_id == context.tenant_id))
    return SubscriptionResponse.model_validate(row, from_attributes=True) if row else None


@router.get("/usage", response_model=dict[str, int])
async def current_usage(
    context: TenantContext = Depends(require_roles("administrador", "supervisor", "agente_comercial")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    return await usage_meters(session, tenant_id=context.tenant_id)


@router.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def create_checkout(
    payload: CheckoutRequest,
    request: Request,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> CheckoutResponse:
    plan = await session.scalar(select(BillingPlan).where(BillingPlan.code == payload.plan_code, BillingPlan.enabled.is_(True)).order_by(BillingPlan.version.desc()))
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "BILLING_PLAN_NOT_FOUND"})
    try:
        checkout = await billing_provider(live_enabled=get_settings().billing_mode == "live").create_checkout(context.tenant_id, plan.code, request.headers.get("Idempotency-Key", "request"))
    except ProviderNotEnabled as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code}) from exc
    return CheckoutResponse(reference=checkout.reference, url=checkout.url)


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_current_subscription(
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    try:
        row = await cancel_subscription(session, tenant_id=context.tenant_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": "SUBSCRIPTION_NOT_FOUND"}) from exc
    return SubscriptionResponse.model_validate(row, from_attributes=True)
