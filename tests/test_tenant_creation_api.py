from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import CurrentIdentity, get_session, require_verified_identity
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import Membership, Tenant, User


@pytest.fixture
async def tenant_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    async with factory.begin() as session:
        session.add(
            User(
                id=user_id,
                name="Existing User",
                email="existing@example.com",
                password_hash=hash_password("existing-password"),
            )
        )

    async def override_session():
        async with factory() as session:
            yield session

    async def override_identity():
        return CurrentIdentity(user_id=user_id)

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_verified_identity] = override_identity
    try:
        yield TestClient(app), factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_user_creates_tenant_without_duplicate_user(tenant_api) -> None:
    client, factory = tenant_api
    response = client.post("/api/v1/tenants", json={"company_name": "Second Company"})
    assert response.status_code == 201
    assert response.json()["slug"] == "second-company"

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 1
        membership = await session.scalar(select(Membership))
        assert membership.role == "administrador"


def test_tenant_creation_requires_authentication() -> None:
    client = TestClient(create_app())
    response = client.post("/api/v1/tenants", json={"company_name": "Second Company"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
