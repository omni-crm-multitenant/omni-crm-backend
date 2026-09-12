from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.crm import Contact, CustomFieldDefinition
from app.models.identity import Membership, Tenant, User
from app.models.operations import AuditEvent, TenantSettings
from tests.support.tenant_isolation import assert_http_cross_tenant_denied


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def business_configuration_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant_a = Tenant(name="Empresa A", slug="configuration-a")
        tenant_b = Tenant(name="Empresa B", slug="configuration-b")
        admin_a = User(name="Admin A", email="config-admin-a@example.com", password_hash=hash_password(PASSWORD), email_verified_at=datetime.now(UTC))
        supervisor_a = User(name="Supervisor A", email="config-supervisor-a@example.com", password_hash=hash_password(PASSWORD), email_verified_at=datetime.now(UTC))
        admin_b = User(name="Admin B", email="config-admin-b@example.com", password_hash=hash_password(PASSWORD), email_verified_at=datetime.now(UTC))
        session.add_all([tenant_a, tenant_b, admin_a, supervisor_a, admin_b])
        await session.flush()
        session.add_all(
            [
                Membership(tenant_id=tenant_a.id, user_id=admin_a.id, role="administrador", status="active"),
                Membership(tenant_id=tenant_a.id, user_id=supervisor_a.id, role="supervisor", status="active"),
                Membership(tenant_id=tenant_b.id, user_id=admin_b.id, role="administrador", status="active"),
            ]
        )
        await session.flush()
        tenant_ids = tenant_a.id, tenant_b.id

    async def override_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    def headers(email: str) -> dict[str, str]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    credentials = {
        "admin_a": headers("config-admin-a@example.com"),
        "supervisor_a": headers("config-supervisor-a@example.com"),
        "admin_b": headers("config-admin-b@example.com"),
    }
    try:
        yield client, factory, tenant_ids, credentials
    finally:
        await engine.dispose()


def valid_settings(name: str = "Empresa A Actualizada") -> dict:
    return {
        "name": name,
        "timezone": "America/Bogota",
        "locale": "es-CO",
        "business_hours": {
            "monday": [{"open": "08:00:00", "close": "12:00:00"}, {"open": "13:00:00", "close": "17:00:00"}],
        },
        "off_hours_policy": {"mode": "auto_reply", "message": "Te responderemos pronto"},
        "contact_info": {"email": "ventas@example.com", "phone": "+57 300 123 4567"},
        "ai_enabled": True,
        "automations_enabled": False,
    }


@pytest.mark.asyncio
async def test_tenant_settings_permissions_validation_isolation_and_audit(business_configuration_api) -> None:
    client, factory, (tenant_a_id, tenant_b_id), credentials = business_configuration_api
    initial = client.get(f"/api/v1/tenants/{tenant_a_id}/settings", headers=credentials["supervisor_a"])
    assert initial.status_code == 200
    assert initial.json()["timezone"] == "America/Bogota"
    assert client.put(
        f"/api/v1/tenants/{tenant_a_id}/settings",
        headers=credentials["supervisor_a"],
        json=valid_settings(),
    ).status_code == 403

    updated = client.put(
        f"/api/v1/tenants/{tenant_a_id}/settings",
        headers=credentials["admin_a"],
        json=valid_settings(),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Empresa A Actualizada"
    assert updated.json()["automations_enabled"] is False
    cross = client.get(f"/api/v1/tenants/{tenant_b_id}/settings", headers=credentials["admin_a"])
    assert_http_cross_tenant_denied(cross, tenant_b_id)

    invalid = valid_settings()
    invalid["business_hours"] = {"monday": [{"open": "17:00:00", "close": "08:00:00"}]}
    assert client.put(
        f"/api/v1/tenants/{tenant_a_id}/settings", headers=credentials["admin_a"], json=invalid
    ).status_code == 422
    bad_timezone = valid_settings()
    bad_timezone["timezone"] = "Nowhere/Unknown"
    assert client.put(
        f"/api/v1/tenants/{tenant_a_id}/settings", headers=credentials["admin_a"], json=bad_timezone
    ).status_code == 422

    async with factory() as session:
        settings = await session.get(TenantSettings, tenant_a_id)
        audit = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_a_id,
                AuditEvent.action == "tenant_settings.updated",
            )
        )
        tenant_b = await session.get(Tenant, tenant_b_id)
        assert settings.automations_enabled is False
        assert audit is not None
        assert tenant_b.name == "Empresa B"


@pytest.mark.asyncio
async def test_custom_field_crud_permissions_isolation_values_and_audit(business_configuration_api) -> None:
    client, factory, (tenant_a_id, _tenant_b_id), credentials = business_configuration_api
    created_a = client.post(
        "/api/v1/custom-fields",
        headers=credentials["admin_a"],
        json={"entity_type": "contact", "name": "segment", "field_type": "select", "options": ["vip", "standard"]},
    )
    assert created_a.status_code == 201
    field_a_id = UUID(created_a.json()["id"])
    created_b = client.post(
        "/api/v1/custom-fields",
        headers=credentials["admin_b"],
        json={"entity_type": "contact", "name": "private_b", "field_type": "text"},
    )
    assert created_b.status_code == 201

    visible_a = client.get("/api/v1/custom-fields", headers=credentials["supervisor_a"])
    assert visible_a.status_code == 200
    assert [item["name"] for item in visible_a.json()] == ["segment"]
    assert client.post(
        "/api/v1/custom-fields",
        headers=credentials["supervisor_a"],
        json={"entity_type": "contact", "name": "forbidden", "field_type": "text"},
    ).status_code == 403
    assert client.get(
        f"/api/v1/custom-fields/{created_b.json()['id']}", headers=credentials["admin_a"]
    ).status_code == 404
    assert client.post(
        "/api/v1/custom-fields",
        headers=credentials["admin_a"],
        json={"entity_type": "contact", "name": "bad", "field_type": "select", "options": []},
    ).status_code == 422

    async with factory.begin() as session:
        session.add(Contact(tenant_id=tenant_a_id, name="Value Holder", tags=[], custom_fields={"segment": "vip"}))
    blocked_type = client.patch(
        f"/api/v1/custom-fields/{field_a_id}",
        headers=credentials["admin_a"],
        json={"field_type": "text"},
    )
    assert blocked_type.status_code == 409
    blocked_delete = client.delete(f"/api/v1/custom-fields/{field_a_id}", headers=credentials["admin_a"])
    assert blocked_delete.status_code == 409
    deleted = client.delete(
        f"/api/v1/custom-fields/{field_a_id}?confirm_values=true", headers=credentials["admin_a"]
    )
    assert deleted.status_code == 204

    async with factory() as session:
        assert await session.get(CustomFieldDefinition, field_a_id) is None
        assert await session.scalar(
            select(func.count()).select_from(AuditEvent).where(
                AuditEvent.tenant_id == tenant_a_id,
                AuditEvent.resource_type == "custom_field_definition",
            )
        ) == 2
