import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.db.base import Base
from app.main import create_app
from app.models.identity import EmailOutbox, Tenant, User


@pytest.fixture
async def registration_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app), factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_creates_company_admin_and_email_intent(registration_api) -> None:
    client, factory = registration_api
    response = client.post(
        "/api/v1/auth/register",
        json={
            "admin_name": "Ana Pérez",
            "email": " ANA@example.com ",
            "password": "correct horse battery staple",
            "company_name": "Clínica Ágil",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "Ana Pérez"
    assert body["user"]["email"] == "ana@example.com"
    assert body["tenant"]["name"] == "Clínica Ágil"
    assert "password" not in str(body).lower()

    async with factory() as session:
        assert await session.scalar(select(Tenant.id)) is not None
        assert await session.scalar(select(User.id)) is not None
        outbox = await session.scalar(select(EmailOutbox))
        assert outbox is not None
        assert outbox.template == "verify_email"


@pytest.mark.asyncio
async def test_duplicate_registration_returns_generic_conflict(registration_api) -> None:
    client, _factory = registration_api
    payload = {
        "admin_name": "Ana Pérez",
        "email": "ana@example.com",
        "password": "correct horse battery staple",
        "company_name": "Clínica Ágil",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"

