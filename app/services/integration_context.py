from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import IntegrationContext
from app.models.identity import ChannelAsset
from app.services.asset_routing import resolve_inbound_asset


@dataclass(frozen=True)
class ValidatedProviderSignature:
    provider: str
    meta_app_id: str


@dataclass(frozen=True)
class IntegrationResolution:
    status: Literal["resolved", "quarantined"]
    context: IntegrationContext | None = None
    reason: Literal["unknown_asset", "ambiguous_asset"] | None = None


@dataclass(frozen=True)
class WorkerEnvelope:
    tenant_id: UUID
    channel_asset_id: UUID
    correlation_id: UUID


async def resolve_integration_context(
    session: AsyncSession,
    *,
    signature: ValidatedProviderSignature,
    channel: str,
    recipient_external_id: str,
    correlation_id: UUID | None = None,
) -> IntegrationResolution:
    routing = await resolve_inbound_asset(
        session,
        meta_app_id=signature.meta_app_id,
        channel=channel,
        recipient_external_id=recipient_external_id,
    )
    if routing.status != "resolved":
        return IntegrationResolution(status="quarantined", reason=routing.reason)
    assert routing.tenant_id is not None and routing.asset_id is not None
    return IntegrationResolution(
        status="resolved",
        context=IntegrationContext(
            tenant_id=routing.tenant_id,
            channel_asset_id=routing.asset_id,
            provider=signature.provider,
            correlation_id=correlation_id or uuid4(),
        ),
    )


def worker_envelope(context: IntegrationContext) -> WorkerEnvelope:
    return WorkerEnvelope(
        tenant_id=context.tenant_id,
        channel_asset_id=context.channel_asset_id,
        correlation_id=context.correlation_id,
    )


async def revalidate_worker_envelope(session: AsyncSession, envelope: WorkerEnvelope) -> bool:
    asset_id = await session.scalar(
        select(ChannelAsset.id).where(
            ChannelAsset.id == envelope.channel_asset_id,
            ChannelAsset.tenant_id == envelope.tenant_id,
            ChannelAsset.status == "connected",
        )
    )
    return asset_id is not None
