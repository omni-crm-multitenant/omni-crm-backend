from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Contact, CustomFieldDefinition


class FieldDefinition(Protocol):
    name: str
    field_type: str
    options: list[str] | None
    required: bool


class CustomFieldValidationError(ValueError):
    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"{field_name}: {reason}")


class ExplicitValueMigrationRequired(ValueError):
    pass


def _allowed_options(definition: FieldDefinition) -> set[str]:
    options = definition.options
    if not isinstance(options, list) or not options or any(not isinstance(item, str) for item in options):
        raise CustomFieldValidationError(definition.name, "select_options_not_configured")
    return set(options)


def validate_custom_field_value(definition: FieldDefinition, value: Any) -> None:
    if value is None:
        if definition.required:
            raise CustomFieldValidationError(definition.name, "required")
        return
    field_type = definition.field_type
    valid = False
    reason = f"expected_{field_type}"
    if field_type == "text":
        valid = isinstance(value, str)
    elif field_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif field_type == "boolean":
        valid = isinstance(value, bool)
    elif field_type == "date":
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
                valid = True
            except ValueError:
                reason = "invalid_iso_date"
    elif field_type == "select":
        valid = isinstance(value, str) and value in _allowed_options(definition)
        reason = "option_not_allowed"
    elif field_type == "multiselect":
        allowed = _allowed_options(definition)
        valid = (
            isinstance(value, list)
            and all(isinstance(item, str) and item in allowed for item in value)
            and len(value) == len(set(value))
        )
        reason = "options_not_allowed_or_duplicated"
    else:
        reason = "unsupported_field_type"
    if not valid:
        raise CustomFieldValidationError(definition.name, reason)


async def validate_custom_field_payload(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    entity_type: str,
    values: dict[str, Any],
    require_all: bool,
) -> None:
    definitions = list(
        await session.scalars(
            select(CustomFieldDefinition).where(
                CustomFieldDefinition.tenant_id == tenant_id,
                CustomFieldDefinition.entity_type == entity_type,
            )
        )
    )
    by_name = {definition.name: definition for definition in definitions}
    unknown = set(values) - set(by_name)
    if unknown:
        name = sorted(unknown)[0]
        raise CustomFieldValidationError(name, "unknown_field")
    if require_all:
        for definition in definitions:
            if definition.required and definition.name not in values:
                raise CustomFieldValidationError(definition.name, "required")
    for name, value in values.items():
        validate_custom_field_value(by_name[name], value)


async def change_custom_field_type(
    session: AsyncSession,
    definition: CustomFieldDefinition,
    new_field_type: str,
) -> None:
    if new_field_type == definition.field_type:
        return
    if await custom_field_has_values(session, definition):
        raise ExplicitValueMigrationRequired("CUSTOM_FIELD_VALUE_MIGRATION_REQUIRED")
    definition.field_type = new_field_type
    definition.options = None


async def custom_field_has_values(
    session: AsyncSession,
    definition: CustomFieldDefinition,
) -> bool:
    if definition.entity_type == "contact":
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            has_value = func.json_type(Contact.custom_fields, f"$.{definition.name}").is_not(None)
        else:
            has_value = Contact.custom_fields.op("?")(definition.name)
        contact_id = await session.scalar(
            select(Contact.id).where(
                Contact.tenant_id == definition.tenant_id,
                has_value,
            ).limit(1)
        )
        return contact_id is not None
    elif definition.entity_type == "opportunity":
        connection = await session.connection()
        has_table = await connection.run_sync(lambda sync_connection: inspect(sync_connection).has_table("opportunities"))
        if has_table:
            if connection.dialect.name == "sqlite":
                statement = text(
                    "SELECT 1 FROM opportunities "
                    "WHERE tenant_id = :tenant_id AND json_type(custom_fields, :json_path) IS NOT NULL LIMIT 1"
                )
                parameters = {"tenant_id": str(definition.tenant_id), "json_path": f"$.{definition.name}"}
            else:
                statement = text(
                    "SELECT 1 FROM opportunities "
                    "WHERE tenant_id = :tenant_id AND custom_fields ? :field_name LIMIT 1"
                )
                parameters = {"tenant_id": definition.tenant_id, "field_name": definition.name}
            return (await session.execute(statement, parameters)).scalar_one_or_none() is not None
    return False
