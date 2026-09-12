import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import EmailOutbox, Invitation, Membership, Tenant, User
from app.services.invitations import hash_invitation_token


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def invitation_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        admin = User(
            name="Admin",
            email="admin@example.com",
            password_hash=hash_password(PASSWORD),
            email_verified_at=datetime.now(UTC),
        )
        tenant = Tenant(name="Empresa", slug="invite-company")
        other = Tenant(name="Otra", slug="other-company")
        session.add_all([admin, tenant, other])
        await session.flush()
        membership = Membership(
            user_id=admin.id,
            tenant_id=tenant.id,
            role="administrador",
            status="active",
        )
        session.add(membership)
        await session.flush()
        ids = admin.id, tenant.id, other.id, membership.id

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
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": PASSWORD},
    ).json()
    try:
        yield client, factory, ids, {"Authorization": f"Bearer {login['access_token']}"}
    finally:
        await engine.dispose()


async def invitation_token(factory) -> str:
    async with factory() as session:
        outbox = await session.scalar(
            select(EmailOutbox).where(EmailOutbox.template == "invitation").order_by(EmailOutbox.created_at.desc())
        )
        return re.search(r"/invitations/([^\s]+)$", outbox.text_body).group(1)


@pytest.mark.asyncio
async def test_admin_invites_and_new_user_accepts_once(invitation_api) -> None:
    client, factory, (_admin_id, tenant_id, _other_id, _membership_id), headers = invitation_api
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        headers=headers,
        json={"email": " NEW@example.com ", "role": "agente_comercial"},
    )
    assert created.status_code == 201
    token = await invitation_token(factory)
    async with factory() as session:
        row = await session.scalar(select(Invitation).where(Invitation.email == "new@example.com"))
        assert row.token_hash == hash_invitation_token(token)
        assert row.token_hash != token
        assert row.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC) + timedelta(days=8)

    details = client.get(f"/api/v1/invitations/{token}")
    assert details.status_code == 200
    assert details.json()["role"] == "agente_comercial"
    accepted = client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"name": "New Agent", "password": "new agent strong password"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["tenant_id"] == str(tenant_id)
    assert client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"name": "Again", "password": "another strong password"},
    ).status_code == 400
    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "new@example.com"))
        membership = await session.scalar(
            select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant_id)
        )
        assert user.email_verified_at is not None
        assert membership.role == "agente_comercial"


@pytest.mark.asyncio
async def test_existing_user_is_linked_without_new_password(invitation_api) -> None:
    client, factory, (_admin_id, tenant_id, _other_id, _membership_id), headers = invitation_api
    async with factory.begin() as session:
        existing = User(name="Existing", email="existing@example.com", password_hash=hash_password(PASSWORD))
        session.add(existing)
    assert client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        headers=headers,
        json={"email": "existing@example.com", "role": "supervisor"},
    ).status_code == 201
    token = await invitation_token(factory)
    accepted = client.post(f"/api/v1/invitations/{token}/accept", json={})
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "supervisor"


@pytest.mark.asyncio
async def test_cross_tenant_role_and_revocation_are_enforced(invitation_api) -> None:
    client, factory, (_admin_id, tenant_id, other_id, membership_id), headers = invitation_api
    assert client.post(
        f"/api/v1/tenants/{other_id}/invitations",
        headers=headers,
        json={"email": "cross@example.com", "role": "supervisor"},
    ).status_code == 403
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        headers=headers,
        json={"email": "revoke@example.com", "role": "supervisor"},
    )
    token = await invitation_token(factory)
    assert client.delete(
        f"/api/v1/tenants/{tenant_id}/invitations/{created.json()['id']}", headers=headers
    ).status_code == 204
    assert client.post(f"/api/v1/invitations/{token}/accept", json={}).status_code == 400

    async with factory.begin() as session:
        membership = await session.get(Membership, membership_id)
        membership.role = "supervisor"
    denied = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        headers=headers,
        json={"email": "forbidden@example.com", "role": "agente_comercial"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_expired_invitation_cannot_be_accepted(invitation_api) -> None:
    client, factory, (_admin_id, tenant_id, _other_id, _membership_id), headers = invitation_api
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/invitations",
        headers=headers,
        json={"email": "expired@example.com", "role": "supervisor"},
    )
    token = await invitation_token(factory)
    async with factory.begin() as session:
        invitation = await session.get(Invitation, UUID(created.json()["id"]))
        invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get(f"/api/v1/invitations/{token}").status_code == 404
    assert client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"name": "Expired", "password": "expired strong password"},
    ).status_code == 400
