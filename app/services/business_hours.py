from __future__ import annotations

from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Tenant
from app.models.operations import TenantSettings


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)


def is_within_business_hours_config(at: datetime, timezone: str, business_hours: dict) -> bool:
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    local = at.astimezone(ZoneInfo(timezone))
    weekday = local.strftime("%A").lower()
    for window in business_hours.get(weekday, []) or []:
        try:
            opening = _parse_time(window["open"])
            closing = _parse_time(window["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if opening <= local.timetz().replace(tzinfo=None) < closing:
            return True
    return False


async def is_within_business_hours(session: AsyncSession, tenant_id: UUID, at: datetime) -> bool:
    tenant = await session.get(Tenant, tenant_id)
    settings = await session.get(TenantSettings, tenant_id)
    if tenant is None or settings is None:
        return False
    return is_within_business_hours_config(at, tenant.timezone, settings.business_hours or {})
