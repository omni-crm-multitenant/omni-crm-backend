import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import get_session
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models.identity import Membership, MfaRecoveryCode, Tenant, User


PASSWORD = "correct horse battery staple"


@pytest.fixture
async def mfa_api():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        user = User(name="MFA User", email="mfa@example.com", password_hash=hash_password(PASSWORD))
        tenant = Tenant(name="MFA Company", slug="mfa-company")
        session.add_all([user, tenant])
        await session.flush()
        session.add(Membership(user_id=user.id, tenant_id=tenant.id, role="administrador", status="active"))

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


def password_login(client):
    return client.post("/api/v1/auth/login", json={"email": "mfa@example.com", "password": PASSWORD})


def bearer(access_token):
    return {"Authorization": f"Bearer {access_token}"}


@pytest.mark.asyncio
async def test_enroll_confirm_and_recovery_codes_are_secure(mfa_api) -> None:
    client, factory = mfa_api
    access = password_login(client).json()["access_token"]
    enrolled = client.post("/api/v1/auth/mfa/enroll", headers=bearer(access))
    assert enrolled.status_code == 200
    secret = enrolled.json()["secret"]
    assert enrolled.json()["provisioning_uri"].startswith("otpauth://totp/")

    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "mfa@example.com"))
        assert user.mfa_enabled is False
        assert user.mfa_secret_encrypted != secret
        assert secret not in user.mfa_secret_encrypted

    confirmed = client.post(
        "/api/v1/auth/mfa/confirm",
        headers=bearer(access),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirmed.status_code == 200
    recovery_codes = confirmed.json()["recovery_codes"]
    assert len(recovery_codes) == len(set(recovery_codes)) == 10
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(MfaRecoveryCode)) == 10
        stored_hashes = set(await session.scalars(select(MfaRecoveryCode.code_hash)))
        assert not stored_hashes.intersection(recovery_codes)

    repeated = client.post(
        "/api/v1/auth/mfa/confirm",
        headers=bearer(access),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert repeated.status_code == 401


@pytest.mark.asyncio
async def test_mfa_login_accepts_totp_and_recovery_code_once(mfa_api) -> None:
    client, _factory = mfa_api
    access = password_login(client).json()["access_token"]
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=bearer(access)).json()
    recovery_codes = client.post(
        "/api/v1/auth/mfa/confirm",
        headers=bearer(access),
        json={"code": pyotp.TOTP(enrollment["secret"]).now()},
    ).json()["recovery_codes"]

    challenged = password_login(client)
    assert challenged.json()["next_step"] == "mfa_required"
    assert challenged.json()["access_token"] is None
    challenge = challenged.json()["challenge_token"]
    totp_result = client.post(
        "/api/v1/auth/mfa/verify",
        json={"challenge_token": challenge, "code": pyotp.TOTP(enrollment["secret"]).now()},
    )
    assert totp_result.status_code == 200
    assert totp_result.json()["next_step"] == "authenticated"

    second_challenge = password_login(client).json()["challenge_token"]
    recovery_result = client.post(
        "/api/v1/auth/mfa/verify",
        json={"challenge_token": second_challenge, "code": recovery_codes[0]},
    )
    assert recovery_result.status_code == 200
    reused = client.post(
        "/api/v1/auth/mfa/verify",
        json={"challenge_token": second_challenge, "code": recovery_codes[0]},
    )
    assert reused.status_code == 401
    assert reused.json() == {"detail": {"code": "INVALID_MFA_FACTOR"}}


@pytest.mark.asyncio
async def test_disable_mfa_requires_password_and_second_factor(mfa_api) -> None:
    client, factory = mfa_api
    access = password_login(client).json()["access_token"]
    enrollment = client.post("/api/v1/auth/mfa/enroll", headers=bearer(access)).json()
    client.post(
        "/api/v1/auth/mfa/confirm",
        headers=bearer(access),
        json={"code": pyotp.TOTP(enrollment["secret"]).now()},
    )
    denied = client.post(
        "/api/v1/auth/mfa/disable",
        headers=bearer(access),
        json={"password": "wrong", "code": pyotp.TOTP(enrollment["secret"]).now()},
    )
    assert denied.status_code == 401
    disabled = client.post(
        "/api/v1/auth/mfa/disable",
        headers=bearer(access),
        json={"password": PASSWORD, "code": pyotp.TOTP(enrollment["secret"]).now()},
    )
    assert disabled.status_code == 200
    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "mfa@example.com"))
        assert user.mfa_enabled is False
        assert user.mfa_secret_encrypted is None
        assert await session.scalar(select(func.count()).select_from(MfaRecoveryCode)) == 0
