from datetime import UTC, datetime
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.core.security import hash_password
from app.core.tokens import decode_token
from app.db.base import Base
from app.main import create_app
from app.models.identity import EmailOutbox, Membership, PasswordResetToken, Tenant, User
from app.services.password_reset import hash_reset_token


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def auth_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

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
    try:
        yield TestClient(app), factory
    finally:
        await engine.dispose()


async def seed_user(factory, *, tenants=1, mfa=False):
    async with factory.begin() as session:
        user = User(
            name="Ana",
            email="ana@example.com",
            password_hash=hash_password(PASSWORD),
            mfa_enabled=mfa,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        memberships = []
        for number in range(tenants):
            tenant = Tenant(name=f"Empresa {number}", slug=f"empresa-{number}")
            membership = Membership(
                user=user,
                tenant=tenant,
                role="administrador" if number == 0 else "agente_comercial",
                status="active",
            )
            session.add_all([tenant, membership])
            memberships.append(membership)
        await session.flush()
        return user.id, [(item.tenant_id, item.id) for item in memberships]


def login(client):
    return client.post("/api/v1/auth/login", json={"email": " ANA@EXAMPLE.COM ", "password": PASSWORD})


@pytest.mark.asyncio
async def test_login_does_not_reveal_unknown_account(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory)
    unknown = client.post("/api/v1/auth/login", json={"email": "none@example.com", "password": "wrong"})
    wrong = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": {"code": "INVALID_CREDENTIALS"}}


@pytest.mark.asyncio
async def test_mfa_challenge_cannot_authorize_business_route(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory, mfa=True)
    response = login(client)
    assert response.json()["next_step"] == "mfa_required"
    challenge = response.json()["challenge_token"]
    assert decode_token(challenge).purpose == "mfa_challenge"
    denied = client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {challenge}"},
        json={"company_name": "No autorizada"},
    )
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_unverified_user_can_login_but_not_access_business_routes(auth_api) -> None:
    client, factory = auth_api
    user_id, _memberships = await seed_user(factory)
    async with factory.begin() as session:
        user = await session.get(User, user_id)
        user.email_verified_at = None
    response = login(client)
    assert response.status_code == 200
    access = response.json()["access_token"]
    denied = client.post(
        "/api/v1/tenants",
        headers={"Authorization": f"Bearer {access}"},
        json={"company_name": "Bloqueada"},
    )
    assert denied.status_code == 403
    assert denied.json() == {"detail": {"code": "EMAIL_NOT_VERIFIED"}}


@pytest.mark.asyncio
async def test_two_tenant_login_requires_explicit_selection(auth_api) -> None:
    client, factory = auth_api
    _user_id, memberships = await seed_user(factory, tenants=2)
    response = login(client)
    body = response.json()
    assert body["next_step"] == "tenant_selection"
    assert body["access_token"] is None
    challenge = body["challenge_token"]

    choices = client.get("/api/v1/auth/memberships", headers={"Authorization": f"Bearer {challenge}"})
    assert choices.status_code == 200
    assert {item["tenant_id"] for item in choices.json()} == {str(item[0]) for item in memberships}

    selected = client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {challenge}"},
        json={"tenant_id": str(memberships[1][0])},
    )
    assert selected.status_code == 200
    claims = decode_token(selected.json()["access_token"], expected_purpose="access")
    assert claims.tenant_id == memberships[1][0]
    assert claims.membership_id == memberships[1][1]


@pytest.mark.asyncio
async def test_inactive_membership_cannot_be_selected(auth_api) -> None:
    client, factory = auth_api
    user_id, memberships = await seed_user(factory, tenants=2)
    challenge = login(client).json()["challenge_token"]
    async with factory.begin() as session:
        membership = await session.get(Membership, memberships[1][1])
        membership.status = "inactive"
    denied = client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {challenge}"},
        json={"tenant_id": str(memberships[1][0])},
    )
    assert user_id is not None
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_active_session_fails_closed_after_membership_deactivation(auth_api) -> None:
    client, factory = auth_api
    _user_id, memberships = await seed_user(factory)
    authenticated = login(client).json()
    async with factory.begin() as session:
        membership = await session.get(Membership, memberships[0][1])
        membership.status = "inactive"
    headers = {"Authorization": f"Bearer {authenticated['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": authenticated["refresh_token"]}
    ).status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_never_changes_its_tenant_binding(auth_api) -> None:
    client, factory = auth_api
    _user_id, memberships = await seed_user(factory, tenants=2)
    challenge = login(client).json()["challenge_token"]
    first = client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {challenge}"},
        json={"tenant_id": str(memberships[0][0])},
    ).json()
    second = client.post(
        "/api/v1/auth/select-tenant",
        headers={"Authorization": f"Bearer {first['access_token']}"},
        json={"tenant_id": str(memberships[1][0])},
    ).json()
    assert second["tenant_id"] == str(memberships[1][0])
    refreshed_first = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert refreshed_first.status_code == 200
    assert refreshed_first.json()["tenant_id"] == str(memberships[0][0])


@pytest.mark.asyncio
async def test_refresh_rotates_once_and_replay_revokes_family(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory)
    authenticated = login(client).json()
    first_refresh = authenticated["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    second_refresh = rotated.json()["refresh_token"]
    assert second_refresh != first_refresh

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "REFRESH_REPLAY_DETECTED"
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh}).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory)
    authenticated = login(client).json()
    headers = {"Authorization": f"Bearer {authenticated['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 401
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": authenticated["refresh_token"]}
    ).status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_is_neutral_and_stores_only_token_hash(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory)
    existing = client.post("/api/v1/auth/forgot-password", json={"email": "ANA@example.com"})
    missing = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json() == {"status": "accepted"}

    async with factory() as session:
        outbox = await session.scalar(select(EmailOutbox).where(EmailOutbox.template == "reset_password"))
        token_row = await session.scalar(select(PasswordResetToken))
        raw_token = re.search(r"token=([^\s]+)", outbox.text_body).group(1)
        assert token_row.token_hash == hash_reset_token(raw_token)
        assert token_row.token_hash != raw_token


@pytest.mark.asyncio
async def test_password_reset_is_single_use_and_revokes_existing_session(auth_api) -> None:
    client, factory = auth_api
    await seed_user(factory)
    authenticated = login(client).json()
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"})
    async with factory() as session:
        outbox = await session.scalar(select(EmailOutbox).where(EmailOutbox.template == "reset_password"))
        raw_token = re.search(r"token=([^\s]+)", outbox.text_body).group(1)

    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "new correct horse battery staple"},
    )
    assert reset.status_code == 200
    reused = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "another correct horse battery staple"},
    )
    assert reused.status_code == 400
    assert client.post(
        "/api/v1/auth/refresh", json={"refresh_token": authenticated["refresh_token"]}
    ).status_code == 401
    old_access = {"Authorization": f"Bearer {authenticated['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=old_access).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "ana@example.com", "password": "new correct horse battery staple"},
    ).status_code == 200
