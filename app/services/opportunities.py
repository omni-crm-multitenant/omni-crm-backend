from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.custom_fields import validate_custom_field_payload


async def validate_opportunity_values(session: AsyncSession, *, tenant_id: UUID, custom_fields: dict[str, Any]) -> None:
    await validate_custom_field_payload(session, tenant_id=tenant_id, entity_type="opportunity", values=custom_fields, require_all=True)


validate_opportunity_custom_fields = validate_opportunity_values
