from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.crm import Contact, CustomFieldDefinition
from app.models.identity import Tenant
from app.services.custom_fields import (
    CustomFieldValidationError,
    ExplicitValueMigrationRequired,
    change_custom_field_type,
    validate_custom_field_value,
)


@dataclass
class Definition:
    name: str
    field_type: str
    options: list[str] | None = None
    required: bool = False


@pytest.mark.parametrize(
    ("definition", "value"),
    [
        (Definition("note", "text"), "hello"),
        (Definition("score", "number"), 2.5),
        (Definition("qualified", "boolean"), True),
        (Definition("birthday", "date"), "2026-09-05"),
        (Definition("size", "select", ["small", "large"]), "large"),
        (Definition("needs", "multiselect", ["crm", "ads"]), ["crm", "ads"]),
    ],
)
def test_supported_custom_field_values(definition, value) -> None:
    validate_custom_field_value(definition, value)


@pytest.mark.parametrize(
    ("definition", "value", "reason"),
    [
        (Definition("note", "text"), 4, "expected_text"),
        (Definition("score", "number"), True, "expected_number"),
        (Definition("birthday", "date"), "09/05/2026", "invalid_iso_date"),
        (Definition("size", "select", ["small"]), "large", "option_not_allowed"),
        (Definition("needs", "multiselect", ["crm"]), ["crm", "crm"], "options_not_allowed_or_duplicated"),
        (Definition("required", "text", required=True), None, "required"),
    ],
)
def test_invalid_custom_field_reports_name_and_reason(definition, value, reason) -> None:
    with pytest.raises(CustomFieldValidationError) as error:
        validate_custom_field_value(definition, value)
    assert error.value.field_name == definition.name
    assert error.value.reason == reason


@pytest.mark.asyncio
async def test_definition_name_is_unique_per_tenant_and_entity() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        tenant = Tenant(name="Custom", slug="custom-unique")
        session.add(tenant)
        await session.flush()
        session.add(CustomFieldDefinition(tenant_id=tenant.id, entity_type="contact", name="size", field_type="text"))
        await session.commit()
        session.add(CustomFieldDefinition(tenant_id=tenant.id, entity_type="contact", name="size", field_type="number"))
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_type_change_requires_explicit_value_migration_when_values_exist() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant = Tenant(name="Custom", slug="custom-migration")
        session.add(tenant)
        await session.flush()
        definition = CustomFieldDefinition(tenant_id=tenant.id, entity_type="contact", name="score", field_type="number")
        contact = Contact(tenant_id=tenant.id, name="Lead", tags=[], custom_fields={"score": 5})
        session.add_all([definition, contact])
        await session.flush()
        with pytest.raises(ExplicitValueMigrationRequired):
            await change_custom_field_type(session, definition, "text")
        assert definition.field_type == "number"
    await engine.dispose()


@pytest.mark.asyncio
async def test_opportunity_type_change_detects_values_when_table_is_available() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("CREATE TABLE opportunities (tenant_id TEXT, custom_fields JSON NOT NULL)"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant = Tenant(name="Opportunity", slug="opportunity-custom")
        session.add(tenant)
        await session.flush()
        definition = CustomFieldDefinition(
            tenant_id=tenant.id,
            entity_type="opportunity",
            name="budget",
            field_type="number",
        )
        session.add(definition)
        await session.flush()
        await session.execute(
            text("INSERT INTO opportunities (tenant_id, custom_fields) VALUES (:tenant_id, :fields)"),
            {"tenant_id": str(tenant.id), "fields": '{"budget": 500}'},
        )
        with pytest.raises(ExplicitValueMigrationRequired):
            await change_custom_field_type(session, definition, "text")
    await engine.dispose()
