from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import ChannelAsset, Membership, MetaOAuthState, Tenant, User
from app.services import meta_oauth
from app.services.credentials import InMemoryCredentialStore


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def meta_oauth_api(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant = Tenant(name="Empresa Meta", slug="meta-oauth")
        user = User(
            name="Admin",
            email="meta-admin@example.com",
            password_hash=hash_password(PASSWORD),
            email_verified_at=datetime.now(UTC),
        )
        session.add_all([tenant, user])
        await session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="administrador", status="active"))
        tenant_id = tenant.id
        user_id = user.id

    monkeypatch.setattr(
        meta_oauth,
        "get_settings",
        lambda: Settings(
            meta_app_id="meta-app-id",
            app_base_url="https://api.example.test",
            meta_graph_api_version="v24.0",
        ),
    )

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
    login = client.post("/api/v1/auth/login", json={"email": "meta-admin@example.com", "password": PASSWORD})
    assert login.status_code == 200
    try:
        yield client, factory, tenant_id, user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_oauth_start_creates_bound_expiring_state(meta_oauth_api) -> None:
    client, factory, tenant_id, user_id, headers = meta_oauth_api
    response = client.get("/api/v1/channel-assets/connect/start?asset_type=whatsapp", headers=headers)

    assert response.status_code == 200
    body = response.json()
    parsed = urlparse(body["authorization_url"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/v24.0/dialog/oauth"
    assert query["client_id"] == ["meta-app-id"]
    assert query["redirect_uri"] == ["https://api.example.test/api/v1/channel-assets/connect/callback"]
    assert query["scope"] == [
        "business_management,whatsapp_business_management,whatsapp_business_messaging"
    ]
    assert len(query["state"][0]) >= 32

    async with factory() as session:
        state = await session.scalar(select(MetaOAuthState).where(MetaOAuthState.tenant_id == tenant_id))
        assert state is not None
        assert state.user_id == user_id
        assert state.asset_type == "whatsapp"
        assert state.redirect_uri == query["redirect_uri"][0]
        assert state.used_at is None
        assert state.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)


@pytest.mark.asyncio
async def test_oauth_start_requires_meta_app_configuration(meta_oauth_api, monkeypatch) -> None:
    client, _factory, _tenant_id, _user_id, headers = meta_oauth_api
    monkeypatch.setattr(meta_oauth, "get_settings", lambda: Settings(meta_app_id=None))

    response = client.get("/api/v1/channel-assets/connect/start?asset_type=instagram", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "META_OAUTH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_oauth_callback_validates_state_exchanges_code_and_discovers_instagram(meta_oauth_api, monkeypatch) -> None:
    client, _factory, _tenant_id, _user_id, headers = meta_oauth_api
    monkeypatch.setattr(
        meta_oauth,
        "get_settings",
        lambda: Settings(
            meta_app_id="meta-app-id",
            meta_app_secret="meta-app-secret",
            app_base_url="https://api.example.test",
            meta_graph_api_version="v24.0",
        ),
    )

    class FakeGraphClient:
        def __init__(self, _settings):
            self.exchange_args = None

        async def exchange_code(self, *, code: str, redirect_uri: str):
            self.exchange_args = code, redirect_uri
            return "page-access-token", None

        async def get(self, path: str, *, access_token: str, params: dict[str, str]):
            assert access_token == "page-access-token"
            assert "fields" in params
            assert path == "/me/accounts"
            return {
                "data": [
                    {
                        "id": "page-1",
                        "name": "Página Uno",
                        "access_token": "page-token-secret",
                        "instagram_business_account": {"id": "instagram-1", "username": "uno"},
                    }
                ]
            }

    monkeypatch.setattr(meta_oauth, "MetaGraphClient", FakeGraphClient)
    credential_store = InMemoryCredentialStore()
    monkeypatch.setattr(meta_oauth, "get_credential_store", lambda: credential_store)
    started = client.get("/api/v1/channel-assets/connect/start?asset_type=instagram", headers=headers)
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]

    callback = client.get(f"/api/v1/channel-assets/connect/callback?state={state}&code=oauth-code")

    assert callback.status_code == 200
    assert callback.json() == {
        "onboarding_status": "ready",
        "asset_type": "instagram",
        "assets": [{"channel": "instagram", "external_id": "instagram-1", "name": "uno"}],
        "error_code": None,
    }
    assert "secret" not in callback.text.lower()

    async with meta_oauth_api[1]() as session:
        asset = await session.scalar(select(ChannelAsset).where(ChannelAsset.external_id == "instagram-1"))
        assert asset is not None
        assert asset.tenant_id == meta_oauth_api[2]
        assert asset.credential_ref != "page-token-secret"
        assert await credential_store.get(asset.credential_ref) == "page-token-secret"

    replay = client.get(f"/api/v1/channel-assets/connect/callback?state={state}&code=oauth-code")
    assert replay.status_code == 400
    assert replay.json()["detail"]["code"] == "INVALID_OAUTH_STATE"


@pytest.mark.asyncio
async def test_oauth_callback_denial_consumes_state_without_leaking_provider_details(meta_oauth_api) -> None:
    client, _factory, _tenant_id, _user_id, headers = meta_oauth_api
    started = client.get("/api/v1/channel-assets/connect/start?asset_type=messenger", headers=headers)
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]

    response = client.get(
        f"/api/v1/channel-assets/connect/callback?state={state}&error=access_denied&error_description=secret-provider-detail"
    )

    assert response.status_code == 200
    assert response.json() == {
        "onboarding_status": "failed",
        "asset_type": "messenger",
        "assets": [],
        "error_code": "META_ACCESS_DENIED",
    }
    assert "secret-provider-detail" not in response.text
