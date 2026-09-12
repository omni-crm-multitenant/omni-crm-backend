from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenant_context import TenantContext
from app.db.base import Base
from app.models.automation_execution import AutomationExecution
from app.models.crm import Consent, Contact, Conversation, Message
from app.models.identity import ChannelAsset, Tenant
from app.services.automation_actions import execute_automation_send
from app.services.consent import has_active_consent
from app.services.send_intent import IdempotencyConflict, create_send_intent


@pytest.fixture
async def safety_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _conversation(session):
    tenant = Tenant(name="Safety", slug=f"safety-{uuid4().hex[:8]}")
    contact = Contact(tenant_id=tenant.id, name="Person", tags=[], custom_fields={})
    asset = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="phone", meta_app_id="app", credential_ref="ref", scopes=[])
    session.add(tenant)
    await session.flush()
    contact.tenant_id = tenant.id
    asset.tenant_id = tenant.id
    session.add_all([contact, asset])
    await session.flush()
    conversation = Conversation(tenant_id=tenant.id, contact_id=contact.id, channel_asset_id=asset.id, channel="whatsapp", status="open")
    session.add(conversation)
    await session.flush()
    return tenant, contact, conversation


@pytest.mark.asyncio
async def test_send_intent_idempotency_replays_and_rejects_changed_payload(safety_database):
    async with safety_database.begin() as session:
        tenant, _, conversation = await _conversation(session)
        context = TenantContext(tenant.id, uuid4(), uuid4(), "supervisor")
        first = await create_send_intent(session, context=context, conversation_id=conversation.id, body_text="hola", idempotency_key="k1")
        replay = await create_send_intent(session, context=context, conversation_id=conversation.id, body_text="hola", idempotency_key="k1")
        assert replay.id == first.id
        with pytest.raises(IdempotencyConflict):
            await create_send_intent(session, context=context, conversation_id=conversation.id, body_text="otro", idempotency_key="k1")


@pytest.mark.asyncio
async def test_latest_consent_and_automation_block_are_explicit(safety_database):
    async with safety_database.begin() as session:
        tenant, contact, conversation = await _conversation(session)
        now = datetime.now(UTC)
        session.add_all([
            Consent(tenant_id=tenant.id, contact_id=contact.id, channel="whatsapp", purpose="marketing", status="granted", source="test", captured_at=now - timedelta(minutes=1)),
            Consent(tenant_id=tenant.id, contact_id=contact.id, channel="whatsapp", purpose="marketing", status="revoked", source="test", captured_at=now),
        ])
        execution = AutomationExecution(tenant_id=tenant.id, rule_id=uuid4(), event_id=uuid4(), rule_version=1, status="processing")
        session.add(execution)
        await session.flush()
        assert await has_active_consent(session, tenant_id=tenant.id, contact_id=contact.id, channel="whatsapp", purpose="marketing") is False
        result = await execute_automation_send(session, execution=execution, conversation_id=conversation.id, body_text="promo", action_id=uuid4())
        assert result is None and execution.status == "blocked"
        assert (await session.scalar(select(Message).where(Message.tenant_id == tenant.id))) is None
