from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.crm import Contact, Conversation, Message
from app.models.identity import ChannelAsset, Tenant


@pytest.fixture
async def conversation_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_context(session):
    nonce = uuid4().hex
    first = Tenant(name="One", slug=f"conversation-one-{nonce[:6]}")
    second = Tenant(name="Two", slug=f"conversation-two-{nonce[6:12]}")
    session.add_all([first, second])
    await session.flush()
    first_contact = Contact(tenant_id=first.id, name="First", tags=[], custom_fields={})
    second_contact = Contact(tenant_id=second.id, name="Second", tags=[], custom_fields={})
    asset = ChannelAsset(tenant_id=first.id, channel="whatsapp", external_id=f"phone-{nonce}", meta_app_id=f"app-{nonce}", credential_ref="opaque", scopes=[])
    session.add_all([first_contact, second_contact, asset])
    await session.flush()
    return first, second, first_contact, second_contact, asset


@pytest.mark.asyncio
async def test_conversation_rejects_mismatched_contact_tenant(conversation_database) -> None:
    async with conversation_database() as session:
        first, _second, _first_contact, second_contact, asset = await seed_context(session)
        session.add(Conversation(tenant_id=first.id, contact_id=second_contact.id, channel_asset_id=asset.id, channel="whatsapp"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_conversation_rejects_asset_channel_mismatch(conversation_database) -> None:
    async with conversation_database() as session:
        first, _second, first_contact, _second_contact, asset = await seed_context(session)
        session.add(Conversation(tenant_id=first.id, contact_id=first_contact.id, channel_asset_id=asset.id, channel="instagram"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_message_provider_identity_and_system_notice_constraints(conversation_database) -> None:
    async with conversation_database() as session:
        first, _second, first_contact, _second_contact, asset = await seed_context(session)
        conversation = Conversation(tenant_id=first.id, contact_id=first_contact.id, channel_asset_id=asset.id, channel="whatsapp")
        session.add(conversation)
        await session.flush()
        occurred_at = datetime.now(UTC)
        session.add(Message(
            tenant_id=first.id, conversation_id=conversation.id, channel_asset_id=asset.id,
            channel="whatsapp", direction="inbound", author_type="contact", body_text="Hola",
            provider_message_id="wamid-1", status="delivered", occurred_at=occurred_at, message_metadata={},
        ))
        await session.commit()
        session.add(Message(
            tenant_id=first.id, conversation_id=conversation.id, channel_asset_id=asset.id,
            channel="whatsapp", direction="inbound", author_type="contact", body_text="Duplicado",
            provider_message_id="wamid-1", status="delivered", occurred_at=occurred_at, message_metadata={},
        ))
        with pytest.raises(IntegrityError):
            await session.commit()

    async with conversation_database() as session:
        first, _second, first_contact, _second_contact, asset = await seed_context(session)
        conversation = Conversation(tenant_id=first.id, contact_id=first_contact.id, channel_asset_id=asset.id, channel="whatsapp")
        session.add(conversation)
        await session.flush()
        session.add(Message(
            tenant_id=first.id, conversation_id=conversation.id, channel_asset_id=asset.id,
            channel="whatsapp", direction="system", author_type="system", body_text="Transferida",
            provider_message_id="must-not-dispatch", status="sent", message_metadata={"event": "handoff"},
        ))
        with pytest.raises(IntegrityError):
            await session.commit()


def test_message_chronology_uses_id_as_tie_breaker() -> None:
    index = next(item for item in Message.__table__.indexes if item.name == "ix_messages_stable_chronology")
    assert tuple(column.name for column in index.columns) == (
        "tenant_id", "conversation_id", "occurred_at", "id"
    )
