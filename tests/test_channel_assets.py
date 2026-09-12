from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.identity import ChannelAsset, Tenant
from app.services.asset_routing import resolve_inbound_asset
from app.services.credentials import CredentialNotFound, InMemoryCredentialStore


@pytest.fixture
async def asset_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_connected_messaging_asset_has_one_owner(asset_database) -> None:
    async with asset_database() as session:
        first = Tenant(name="Uno", slug=f"uno-{uuid4().hex[:6]}")
        second = Tenant(name="Dos", slug=f"dos-{uuid4().hex[:6]}")
        session.add_all([first, second])
        await session.flush()
        session.add(ChannelAsset(tenant_id=first.id, channel="whatsapp", external_id="phone-1", meta_app_id="app-1", credential_ref="ref-1", scopes=[]))
        await session.commit()
        session.add(ChannelAsset(tenant_id=second.id, channel="whatsapp", external_id="phone-1", meta_app_id="app-1", credential_ref="ref-2", scopes=[]))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_tenant_can_own_multiple_distinct_assets_and_ad_accounts_are_separate(asset_database) -> None:
    async with asset_database.begin() as session:
        tenant = Tenant(name="Uno", slug="multi-assets")
        session.add(tenant)
        await session.flush()
        session.add_all([
            ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="one", meta_app_id="app", credential_ref="ref-1", scopes=[]),
            ChannelAsset(tenant_id=tenant.id, channel="instagram", external_id="two", meta_app_id="app", credential_ref="ref-2", scopes=[]),
            ChannelAsset(tenant_id=tenant.id, channel="ad_account", external_id="ads", meta_app_id="app", credential_ref="ref-3", scopes=["ads_read"]),
            ChannelAsset(tenant_id=tenant.id, channel="ad_account", external_id="ads", meta_app_id="app", credential_ref="ref-4", scopes=["ads_read"]),
        ])


@pytest.mark.asyncio
async def test_routing_resolves_exact_asset_and_quarantines_unknown(asset_database) -> None:
    async with asset_database.begin() as session:
        tenant = Tenant(name="Uno", slug="routing")
        session.add(tenant)
        await session.flush()
        asset = ChannelAsset(tenant_id=tenant.id, channel="messenger", external_id="page-1", meta_app_id="app", credential_ref="opaque", scopes=[])
        session.add(asset)
    async with asset_database() as session:
        resolved = await resolve_inbound_asset(session, meta_app_id="app", channel="messenger", recipient_external_id="page-1")
        unknown = await resolve_inbound_asset(session, meta_app_id="app", channel="messenger", recipient_external_id="missing")
        assert resolved.status == "resolved" and resolved.tenant_id == tenant.id
        assert unknown.status == "quarantined" and unknown.reason == "unknown_asset"


@pytest.mark.asyncio
async def test_credentials_are_opaque_and_deletable() -> None:
    store = InMemoryCredentialStore()
    secret = "EAAB-provider-token"
    reference = await store.put(secret)
    assert secret not in reference
    assert await store.get(reference) == secret
    await store.delete(reference)
    with pytest.raises(CredentialNotFound):
        await store.get(reference)


@pytest.mark.asyncio
async def test_ambiguous_routing_is_quarantined_without_business_write() -> None:
    first = ChannelAsset(id=uuid4(), tenant_id=uuid4(), channel="whatsapp", external_id="same", meta_app_id="app", credential_ref="one", scopes=[])
    second = ChannelAsset(id=uuid4(), tenant_id=uuid4(), channel="whatsapp", external_id="same", meta_app_id="app", credential_ref="two", scopes=[])

    class CorruptRoutingSession:
        async def scalars(self, _statement):
            return [first, second]

    result = await resolve_inbound_asset(
        CorruptRoutingSession(),
        meta_app_id="app",
        channel="whatsapp",
        recipient_external_id="same",
    )
    assert result.status == "quarantined"
    assert result.reason == "ambiguous_asset"
    assert result.tenant_id is None and result.asset_id is None
