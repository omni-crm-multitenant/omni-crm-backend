from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import CurrentIdentity, get_session, require_verified_identity
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import EmailVerificationToken, User
from app.services.email_verification import (
    InvalidVerificationToken,
    hash_verification_token,
    issue_verification_token,
    verify_email_token,
)


@pytest.fixture
async def verification_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    async with factory.begin() as session:
        session.add(
            User(
                id=user_id,
                name="Verify User",
                email="verify@example.com",
                password_hash=hash_password("strong-password"),
            )
        )
    try:
        yield factory, user_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_token_is_hashed_and_single_use(verification_database) -> None:
    factory, user_id = verification_database
    async with factory.begin() as session:
        raw_token = await issue_verification_token(session, user_id)

    async with factory.begin() as session:
        user = await verify_email_token(session, raw_token)
        assert user.email_verified_at is not None

    async with factory.begin() as session:
        with pytest.raises(InvalidVerificationToken):
            await verify_email_token(session, raw_token)

    assert raw_token != hash_verification_token(raw_token)


@pytest.mark.asyncio
async def test_expired_token_is_rejected(verification_database) -> None:
    factory, user_id = verification_database
    raw_token = "expired-token-value-with-at-least-32-characters"
    async with factory.begin() as session:
        session.add(
            EmailVerificationToken(
                user_id=user_id,
                token_hash=hash_verification_token(raw_token),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    async with factory.begin() as session:
        with pytest.raises(InvalidVerificationToken):
            await verify_email_token(session, raw_token)


@pytest.mark.asyncio
async def test_verify_email_endpoint_uses_generic_error(verification_database) -> None:
    factory, user_id = verification_database
    async with factory.begin() as session:
        raw_token = await issue_verification_token(session, user_id)

    async def override_session():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)

    assert client.get("/api/v1/auth/verify-email", params={"token": raw_token}).status_code == 200
    reused = client.get("/api/v1/auth/verify-email", params={"token": raw_token})
    assert reused.status_code == 400
    assert reused.json()["detail"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


@pytest.mark.asyncio
async def test_sensitive_write_gate_requires_verified_email(verification_database) -> None:
    factory, user_id = verification_database
    identity = CurrentIdentity(user_id=user_id)
    async with factory() as session:
        with pytest.raises(HTTPException) as denied:
            await require_verified_identity(identity, session)
        assert denied.value.status_code == 403
        assert denied.value.detail["code"] == "EMAIL_NOT_VERIFIED"

    async with factory.begin() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        user.email_verified_at = datetime.now(UTC)

    async with factory() as session:
        assert await require_verified_identity(identity, session) == identity
