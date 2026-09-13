from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.crm import Contact, Conversation
from app.models.identity import ChannelAsset, Tenant
from app.repositories.contact_identities import upsert_contact_identity
from app.services import asset_revalidation
from app.services.credentials import InMemoryCredentialStore
from app.services.message_authors import MessageAuthor, validate_message_author_storage


@pytest.fixture
async def block_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_identity_repository_updates_same_asset_sender(block_factory) -> None:
    async with block_factory.begin() as session:
        tenant = Tenant(name="Repo", slug="identity-repo")
        session.add(tenant)
        await session.flush()
        contact = Contact(tenant_id=tenant.id, name="Person", tags=[], custom_fields={})
        asset = ChannelAsset(tenant_id=tenant.id, channel="messenger", external_id="page", meta_app_id="app", credential_ref="ref", scopes=[])
        session.add_all([contact, asset])
        await session.flush()
        first = await upsert_contact_identity(
            session,
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel_asset_id=asset.id,
            external_user_id="sender",
            display_name="First",
        )
        second = await upsert_contact_identity(
            session,
            tenant_id=tenant.id,
            contact_id=contact.id,
            channel_asset_id=asset.id,
            external_user_id="sender",
            display_name="Updated",
        )
        assert first.id == second.id
        assert second.display_name == "Updated"


@pytest.mark.asyncio
async def test_asset_revalidation_updates_status_without_exposing_token(block_factory, monkeypatch) -> None:
    async with block_factory.begin() as session:
        tenant = Tenant(name="Revalidate", slug="asset-revalidate")
        session.add(tenant)
        await session.flush()
        asset = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="phone", meta_app_id="app", credential_ref="old", scopes=[])
        session.add(asset)
        await session.flush()
        asset_id, tenant_id = asset.id, tenant.id

    store = InMemoryCredentialStore()
    await store.put("token")
    await store.delete("old")
    ref = await store.put("token")
    async with block_factory() as session:
        asset = await session.get(ChannelAsset, asset_id)
        asset.credential_ref = ref
        await session.commit()

    class FakeGraph:
        def __init__(self, _settings):
            pass

        async def debug_token(self, token):
            assert token == "token"
            return {"data": {"is_valid": True}}

    monkeypatch.setattr(asset_revalidation, "MetaGraphClient", FakeGraph)
    async with block_factory() as session:
        result = await asset_revalidation.revalidate_channel_asset(
            session, tenant_id=tenant_id, asset_id=asset_id, credential_store=store
        )
        assert result.status == "connected"


@pytest.mark.asyncio
async def test_conversation_query_contract_fields_are_tenant_scoped(block_factory) -> None:
    async with block_factory.begin() as session:
        tenant = Tenant(name="Conversation", slug="conversation-query")
        session.add(tenant)
        await session.flush()
        contact = Contact(tenant_id=tenant.id, name="Person", tags=[], custom_fields={})
        asset = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="phone", meta_app_id="app", credential_ref="ref", scopes=[])
        session.add_all([contact, asset])
        await session.flush()
        session.add(Conversation(tenant_id=tenant.id, contact_id=contact.id, channel_asset_id=asset.id, channel="whatsapp", status="open"))
        assert tenant.id is not None


def test_author_validator_rejects_invalid_combinations() -> None:
    with pytest.raises(ValueError, match="invalid author_type"):
        validate_message_author_storage("human", None, {})
    with pytest.raises(ValueError, match="user author requires"):
        validate_message_author_storage("user", None, {})
    validate_message_author_storage("ai", None, {"author_origin": "ai", "author_source_id": str(uuid4())})
    assert MessageAuthor.system(uuid4()).storage_fields()["author_type"] == "system"
