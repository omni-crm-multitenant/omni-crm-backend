from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.identity import Membership, Tenant, User
from app.repositories.memberships import get_membership, list_memberships


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


async def seed_user_and_tenants(session):
    user = User(name="Ana", email="ana@example.com", password_hash="hash")
    first = Tenant(name="Uno", slug=f"uno-{uuid4().hex[:6]}")
    second = Tenant(name="Dos", slug=f"dos-{uuid4().hex[:6]}")
    session.add_all([user, first, second])
    await session.flush()
    return user, first, second


@pytest.mark.asyncio
async def test_memberships_are_listed_only_for_requested_user(session_factory) -> None:
    async with session_factory() as session:
        user, first, second = await seed_user_and_tenants(session)
        session.add_all(
            [
                Membership(user_id=user.id, tenant_id=first.id, role="administrador"),
                Membership(user_id=user.id, tenant_id=second.id, role="agente_comercial"),
            ]
        )
        await session.commit()

        memberships = await list_memberships(session, user_id=user.id)

        assert {item.tenant_id for item in memberships} == {first.id, second.id}
        assert {item.role for item in memberships} == {"administrador", "agente_comercial"}
        assert await get_membership(session, user_id=user.id, tenant_id=second.id) is not None
        assert await get_membership(session, user_id=uuid4(), tenant_id=second.id) is None


@pytest.mark.asyncio
async def test_membership_pair_is_unique(session_factory) -> None:
    async with session_factory() as session:
        user, tenant, _ = await seed_user_and_tenants(session)
        session.add(Membership(user_id=user.id, tenant_id=tenant.id, role="supervisor"))
        await session.commit()
        session.add(Membership(user_id=user.id, tenant_id=tenant.id, role="agente_comercial"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_membership_role_is_constrained(session_factory) -> None:
    async with session_factory() as session:
        user, tenant, _ = await seed_user_and_tenants(session)
        session.add(Membership(user_id=user.id, tenant_id=tenant.id, role="agente"))
        with pytest.raises(IntegrityError):
            await session.commit()
