from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenant_context import TenantContext
from app.db.base import Base
from app.models.crm import Contact, CustomFieldDefinition
from app.models.identity import Tenant
from app.repositories.contacts import ContactNotFound, create_contact, update_contact
from app.services.custom_fields import CustomFieldValidationError


def tenant_context(tenant_id):
    return TenantContext(tenant_id=tenant_id, membership_id=uuid4(), user_id=uuid4(), role="administrador")


@pytest.mark.asyncio
async def test_contact_repository_validates_custom_fields_and_scopes_tenant() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        first = Tenant(name="One", slug="contact-one")
        second = Tenant(name="Two", slug="contact-two")
        session.add_all([first, second])
        await session.flush()
        session.add_all([
            CustomFieldDefinition(tenant_id=first.id, entity_type="contact", name="segment", field_type="select", options=["vip", "standard"], required=True),
            CustomFieldDefinition(tenant_id=second.id, entity_type="contact", name="private", field_type="text"),
        ])
        await session.flush()
        contact = await create_contact(
            session,
            tenant_context(first.id),
            name=" Lead ",
            email=" LEAD@EXAMPLE.COM ",
            phone="+573001112233",
            tags=["meta"],
            custom_fields={"segment": "vip"},
        )
        assert contact.tenant_id == first.id
        assert contact.email == "lead@example.com"
        with pytest.raises(CustomFieldValidationError, match="unknown_field"):
            await update_contact(session, tenant_context(first.id), contact.id, custom_fields={"private": "leak"})
        with pytest.raises(ContactNotFound):
            await update_contact(session, tenant_context(second.id), contact.id, name="Cross tenant")
    await engine.dispose()


def test_contact_dedup_indexes_are_tenant_scoped() -> None:
    indexes = {index.name: tuple(column.name for column in index.columns) for index in Contact.__table__.indexes}
    assert indexes["ix_contacts_tenant_phone"] == ("tenant_id", "phone")
    assert indexes["ix_contacts_tenant_email"] == ("tenant_id", "email")
