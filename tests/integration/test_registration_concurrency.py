import asyncio
import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.db.base import Base
from app.main import create_app
from app.models.identity import Membership, Tenant, User
from app.core.security import hash_password
from app.services.sessions import RefreshReplay, issue_session_pair, rotate_refresh_token


DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is required")
@pytest.mark.asyncio
async def test_simultaneous_registration_accepts_exactly_one_request() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    payload = {
        "admin_name": "Ana Pérez",
        "email": " Race@Example.com ",
        "password": "correct horse battery staple",
        "company_name": "Empresa Concurrente",
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            responses = await asyncio.gather(
                client.post("/api/v1/auth/register", json=payload),
                client.post("/api/v1/auth/register", json={**payload, "email": "race@example.COM"}),
            )
        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json() == {"detail": {"code": "EMAIL_ALREADY_REGISTERED"}}
    finally:
        await engine.dispose()


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is required")
@pytest.mark.asyncio
async def test_concurrent_refresh_consumes_token_once() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory.begin() as session:
            user = User(name="Ana", email="refresh@example.com", password_hash=hash_password("strong-password"))
            tenant = Tenant(name="Empresa", slug="refresh-company")
            membership = Membership(user=user, tenant=tenant, role="administrador", status="active")
            session.add_all([user, tenant, membership])
            await session.flush()
            pair = await issue_session_pair(session, user_id=user.id, membership=membership)

        async def rotate():
            async with factory() as session:
                try:
                    result = await rotate_refresh_token(session, pair.refresh_token)
                    await session.commit()
                    return result
                except RefreshReplay as exc:
                    return exc

        outcomes = await asyncio.gather(rotate(), rotate())
        assert sum(not isinstance(item, Exception) for item in outcomes) == 1
        assert sum(isinstance(item, RefreshReplay) for item in outcomes) == 1
    finally:
        await engine.dispose()
