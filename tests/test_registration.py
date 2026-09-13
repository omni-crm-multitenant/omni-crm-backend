import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import verify_password
from app.db.base import Base
from app.models.identity import Membership, Tenant, User
from app.services.registration import EmailAlreadyRegisteredError, register_company, slugify


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_register_company_is_atomic_and_normalizes_email(session_factory) -> None:
    async with session_factory() as session:
        result = await register_company(
            session,
            company_name="Clínica Ágil",
            admin_name="Ana Pérez",
            admin_email=" ANA@EXAMPLE.COM ",
            admin_password="correct horse battery staple",
        )
        assert result.tenant.slug == "clinica-agil"
        assert result.user.email == "ana@example.com"
        assert result.membership.role == "administrador"
        assert verify_password(result.user.password_hash, "correct horse battery staple")


@pytest.mark.asyncio
async def test_duplicate_email_rolls_back_second_registration(session_factory) -> None:
    async with session_factory() as session:
        await register_company(session, "Empresa Uno", "Ana", "ana@example.com", "strong-password")
        with pytest.raises(EmailAlreadyRegisteredError):
            await register_company(session, "Empresa Dos", "Ana", "ANA@example.com", "strong-password")

        tenant_count = len((await session.execute(Tenant.__table__.select())).all())
        user_count = len((await session.execute(User.__table__.select())).all())
        membership_count = len((await session.execute(Membership.__table__.select())).all())
        assert (tenant_count, user_count, membership_count) == (1, 1, 1)


@pytest.mark.asyncio
async def test_membership_failure_rolls_back_tenant_and_user(session_factory) -> None:
    async with session_factory() as session:
        def fail_membership(sync_session, _flush_context, _instances) -> None:
            if any(isinstance(item, Membership) for item in sync_session.new):
                raise RuntimeError("membership failure")

        event.listen(session.sync_session, "before_flush", fail_membership)
        with pytest.raises(RuntimeError, match="membership failure"):
            await register_company(session, "Empresa Fallida", "Ana", "fallo@example.com", "strong-password")
        event.remove(session.sync_session, "before_flush", fail_membership)

        assert await session.scalar(select(Tenant.id)) is None
        assert await session.scalar(select(User.id)) is None


@pytest.mark.asyncio
async def test_verification_intent_failure_rolls_back_identity(session_factory) -> None:
    async def fail_intent(_session, _result) -> None:
        raise RuntimeError("outbox failure")

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="outbox failure"):
            await register_company(
                session,
                "Empresa Fallida",
                "Ana",
                "outbox@example.com",
                "strong-password",
                after_identity_created=fail_intent,
            )

        assert await session.scalar(select(Tenant.id)) is None
        assert await session.scalar(select(User.id)) is None
        assert await session.scalar(select(Membership.id)) is None


@pytest.mark.asyncio
async def test_slug_collision_adds_short_suffix(session_factory) -> None:
    async with session_factory() as session:
        first = await register_company(session, "Empresa Uno", "Ana", "ana@example.com", "strong-password")
        second = await register_company(session, "Empresa Uno", "Beto", "beto@example.com", "strong-password")

        assert first.tenant.slug == "empresa-uno"
        assert second.tenant.slug.startswith("empresa-uno-")
        assert len(second.tenant.slug) <= 120


def test_slugify_is_deterministic() -> None:
    assert slugify(" Clínica Ágil ") == "clinica-agil"
