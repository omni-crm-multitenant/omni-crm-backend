from datetime import time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.identity import Tenant
from app.models.operations import TenantSettings
from app.services.audit import write_audit_event
from app.services.authorization import require_roles


router = APIRouter(prefix="/tenants/{tenant_id}/settings", tags=["tenant-settings"])


class TimeWindow(BaseModel):
    open: time
    close: time

    @model_validator(mode="after")
    def close_after_open(self):
        if self.close <= self.open:
            raise ValueError("close must be after open")
        return self


class BusinessHours(BaseModel):
    monday: list[TimeWindow] = Field(default_factory=list)
    tuesday: list[TimeWindow] = Field(default_factory=list)
    wednesday: list[TimeWindow] = Field(default_factory=list)
    thursday: list[TimeWindow] = Field(default_factory=list)
    friday: list[TimeWindow] = Field(default_factory=list)
    saturday: list[TimeWindow] = Field(default_factory=list)
    sunday: list[TimeWindow] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_overlaps(self):
        for weekday in type(self).model_fields:
            windows = sorted(getattr(self, weekday), key=lambda item: item.open)
            if any(current.open < previous.close for previous, current in zip(windows, windows[1:])):
                raise ValueError(f"overlapping windows for {weekday}")
        return self


class OffHoursPolicy(BaseModel):
    mode: Literal["queue", "auto_reply"] = "queue"
    message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def auto_reply_has_message(self):
        if self.mode == "auto_reply" and not self.message:
            raise ValueError("auto_reply requires message")
        return self


class ContactInfo(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)


class TenantSettingsPayload(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    timezone: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=10)
    business_hours: BusinessHours = Field(default_factory=BusinessHours)
    off_hours_policy: OffHoursPolicy = Field(default_factory=OffHoursPolicy)
    contact_info: ContactInfo = Field(default_factory=ContactInfo)
    ai_enabled: bool = True
    automations_enabled: bool = True
    max_output_tokens: int = Field(default=512, ge=1, le=20000)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_tool_calls: int = Field(default=8, ge=0, le=100)
    max_retries: int = Field(default=2, ge=0, le=10)
    monthly_token_budget: int = Field(default=100000, ge=1)

    @model_validator(mode="after")
    def valid_timezone(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown timezone") from exc
        return self


async def _load_settings(session: AsyncSession, tenant_id: UUID) -> tuple[Tenant, TenantSettings]:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail={"code": "TENANT_NOT_FOUND"})
    settings = await session.get(TenantSettings, tenant_id)
    if settings is None:
        settings = TenantSettings(tenant_id=tenant_id, business_hours={}, off_hours_policy={}, contact_info={})
        session.add(settings)
        await session.flush()
    return tenant, settings


def _response(tenant: Tenant, settings: TenantSettings) -> TenantSettingsPayload:
    return TenantSettingsPayload(
        name=tenant.name,
        timezone=tenant.timezone,
        locale=tenant.locale,
        business_hours=settings.business_hours,
        off_hours_policy=settings.off_hours_policy,
        contact_info=settings.contact_info,
        ai_enabled=settings.ai_enabled,
        automations_enabled=settings.automations_enabled,
        max_output_tokens=settings.max_output_tokens,
        timeout_seconds=settings.timeout_seconds,
        max_tool_calls=settings.max_tool_calls,
        max_retries=settings.max_retries,
        monthly_token_budget=settings.monthly_token_budget,
    )


@router.get("", response_model=TenantSettingsPayload)
async def get_settings(
    tenant_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> TenantSettingsPayload:
    if tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "CROSS_TENANT_ACCESS_DENIED"})
    tenant, settings = await _load_settings(session, context.tenant_id)
    return _response(tenant, settings)


@router.put("", response_model=TenantSettingsPayload)
async def update_settings(
    tenant_id: UUID,
    payload: TenantSettingsPayload,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> TenantSettingsPayload:
    if tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "CROSS_TENANT_ACCESS_DENIED"})
    tenant, settings = await _load_settings(session, context.tenant_id)
    before = _response(tenant, settings).model_dump(mode="json")
    tenant.name = payload.name.strip()
    tenant.timezone = payload.timezone
    tenant.locale = payload.locale
    settings.business_hours = payload.business_hours.model_dump(mode="json")
    settings.off_hours_policy = payload.off_hours_policy.model_dump(mode="json")
    settings.contact_info = payload.contact_info.model_dump(mode="json")
    settings.ai_enabled = payload.ai_enabled
    settings.automations_enabled = payload.automations_enabled
    settings.max_output_tokens = payload.max_output_tokens
    settings.timeout_seconds = payload.timeout_seconds
    settings.max_tool_calls = payload.max_tool_calls
    settings.max_retries = payload.max_retries
    settings.monthly_token_budget = payload.monthly_token_budget
    after = payload.model_dump(mode="json")
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="tenant_settings.updated",
        resource_type="tenant_settings",
        resource_id=context.tenant_id,
        metadata={"before": before, "after": after},
    )
    return _response(tenant, settings)
