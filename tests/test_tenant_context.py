from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.dependencies import CurrentIdentity, require_tenant_context
from app.db.base import Base
from app.models.identity import ChannelAsset, Membership, Tenant, User
from app.services.integration_context import (
    ValidatedProviderSignature,
    revalidate_worker_envelope,
    resolve_integration_context,
    worker_envelope,
)


@pytest.fixture
async def context_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory.begin() as session:
        tenant = Tenant(name="Empresa", slug=f"context-{uuid4().hex[:6]}")
        user = User(name="Ana", email=f"{uuid4().hex}@example.com", password_hash="hash")
        session.add_all([tenant, user])
        await session.flush()
        membership = Membership(tenant_id=tenant.id, user_id=user.id, role="agente_comercial", status="active")
        asset = ChannelAsset(tenant_id=tenant.id, channel="whatsapp", external_id="phone", meta_app_id="meta-app", credential_ref="opaque", scopes=[])
        session.add_all([membership, asset])
        await session.flush()
        ids = tenant.id, user.id, membership.id, asset.id
    try:
        yield factory, ids
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_context_reads_current_role_and_rejects_disabled_membership(context_database) -> None:
    factory, (tenant_id, user_id, membership_id, _asset_id) = context_database
    identity = CurrentIdentity(user_id=user_id, tenant_id=tenant_id, membership_id=membership_id, session_id=uuid4())
    async with factory() as session:
        context = await require_tenant_context(identity, session)
        assert context.tenant_id == tenant_id
        assert context.role == "agente_comercial"
    async with factory.begin() as session:
        membership = await session.get(Membership, membership_id)
        membership.role = "supervisor"
    async with factory() as session:
        assert (await require_tenant_context(identity, session)).role == "supervisor"
    async with factory.begin() as session:
        membership = await session.get(Membership, membership_id)
        membership.status = "inactive"
    async with factory() as session:
        with pytest.raises(HTTPException) as denied:
            await require_tenant_context(identity, session)
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_integration_context_comes_only_from_registered_asset(context_database) -> None:
    factory, (tenant_id, _user_id, _membership_id, asset_id) = context_database
    signature = ValidatedProviderSignature(provider="meta", meta_app_id="meta-app")
    async with factory() as session:
        resolved = await resolve_integration_context(
            session,
            signature=signature,
            channel="whatsapp",
            recipient_external_id="phone",
        )
        unknown = await resolve_integration_context(
            session,
            signature=signature,
            channel="whatsapp",
            recipient_external_id=str(tenant_id),
        )
        assert resolved.context.tenant_id == tenant_id
        assert resolved.context.channel_asset_id == asset_id
        assert unknown.status == "quarantined" and unknown.context is None


@pytest.mark.asyncio
async def test_worker_revalidates_asset_ownership_before_effects(context_database) -> None:
    factory, (tenant_id, _user_id, _membership_id, _asset_id) = context_database
    async with factory() as session:
        resolution = await resolve_integration_context(
            session,
            signature=ValidatedProviderSignature(provider="meta", meta_app_id="meta-app"),
            channel="whatsapp",
            recipient_external_id="phone",
        )
        envelope = worker_envelope(resolution.context)
        assert await revalidate_worker_envelope(session, envelope)
        forged = type(envelope)(tenant_id=uuid4(), channel_asset_id=envelope.channel_asset_id, correlation_id=envelope.correlation_id)
        assert not await revalidate_worker_envelope(session, forged)
