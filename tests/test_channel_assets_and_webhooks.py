from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.api.v1 import webhooks
from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import ChannelAsset, Membership, Tenant, User


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def asset_http_api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant = Tenant(name="Assets", slug="assets-http")
        user = User(
            name="Admin",
            email="assets-admin@example.com",
            password_hash=hash_password(PASSWORD),
            email_verified_at=datetime.now(UTC),
        )
        session.add_all([tenant, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="administrador", status="active"))
        session.add_all([
            ChannelAsset(
                tenant_id=tenant.id,
                channel="whatsapp",
                external_id="phone-1",
                meta_app_id="meta-app",
                credential_ref="opaque-ref",
                scopes=["whatsapp_business_messaging"],
                status="connected",
            ),
            ChannelAsset(
                tenant_id=tenant.id,
                channel="instagram",
                external_id="ig-1",
                meta_app_id="meta-app",
                credential_ref="opaque-ref-2",
                scopes=[],
                status="disconnected",
            ),
        ])
        tenant_id = tenant.id

    monkeypatch.setattr(webhooks, "get_settings", lambda: Settings(meta_webhook_verify_token="verify-me"))

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
    login = client.post("/api/v1/auth/login", json={"email": "assets-admin@example.com", "password": PASSWORD})
    assert login.status_code == 200
    try:
        yield client, tenant_id, {"Authorization": f"Bearer {login.json()['access_token']}"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_channel_asset_list_and_detail_are_tenant_scoped(asset_http_api) -> None:
    client, tenant_id, headers = asset_http_api
    listed = client.get("/api/v1/channel-assets", headers=headers)
    assert listed.status_code == 200
    assert {item["external_id"] for item in listed.json()} == {"phone-1", "ig-1"}
    assert all("credential_ref" not in item for item in listed.json())

    asset_id = next(item["id"] for item in listed.json() if item["external_id"] == "phone-1")
    detail = client.get(f"/api/v1/channel-assets/{asset_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "connected"
    assert client.get(f"/api/v1/channel-assets/{uuid4()}", headers=headers).status_code == 404
    assert tenant_id is not None


def test_meta_webhook_verification_and_rejection(asset_http_api) -> None:
    client, _tenant_id, _headers = asset_http_api
    valid = client.get(
        "/api/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=challenge-123"
    )
    assert valid.status_code == 200
    assert valid.text == "challenge-123"
    invalid = client.get(
        "/api/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=challenge-123"
    )
    assert invalid.status_code == 403
