from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.crm import Contact
from app.services.integration_context import WorkerEnvelope
from tests.support.tenant_isolation import (
    assert_same_tenant_unassigned_denied,
    assert_worker_cross_tenant_denied,
    seed_two_tenant_fixture,
)


@pytest.mark.asyncio
async def test_deterministic_two_tenant_fixture_and_reusable_assertions() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed_two_tenant_fixture(session)
    async with factory() as session:
        own = list(await session.scalars(select(Contact).where(Contact.tenant_id == ids.tenant_a_id)))
        assert [row.id for row in own] == [ids.contact_a_id]
        await assert_worker_cross_tenant_denied(
            session,
            WorkerEnvelope(
                tenant_id=ids.tenant_b_id,
                channel_asset_id=ids.asset_a_id,
                correlation_id=uuid4(),
            ),
        )
    assert_same_tenant_unassigned_denied(ids)
    await engine.dispose()
