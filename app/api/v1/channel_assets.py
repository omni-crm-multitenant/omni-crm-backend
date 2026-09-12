from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.identity import ChannelAsset
from app.services.authorization import require_roles
from app.services.meta_oauth import (
    MetaAssetType,
    MetaOAuthError,
    MetaOAuthNotConfigured,
    InvalidOAuthState,
    complete_meta_oauth,
    reject_meta_oauth,
    start_meta_oauth,
)
from app.services.asset_revalidation import revalidate_channel_asset
from app.services.audit import write_audit_event
from app.services.credentials import get_credential_store


router = APIRouter(prefix="/channel-assets", tags=["channel-assets"])


class OAuthStartResponse(BaseModel):
    authorization_url: str
    asset_type: MetaAssetType
    state_expires_at: datetime


class DiscoveredMetaAsset(BaseModel):
    channel: MetaAssetType
    external_id: str
    name: str | None = None


class OAuthCallbackResponse(BaseModel):
    onboarding_status: str
    asset_type: MetaAssetType | None = None
    assets: list[DiscoveredMetaAsset] = Field(default_factory=list)
    error_code: str | None = None


class ChannelAssetResponse(BaseModel):
    id: str
    channel: MetaAssetType
    external_id: str
    meta_app_id: str
    scopes: list[str]
    credential_expires_at: datetime | None
    status: str


def _asset_response(asset: ChannelAsset) -> ChannelAssetResponse:
    return ChannelAssetResponse(
        id=str(asset.id),
        channel=MetaAssetType(asset.channel),
        external_id=asset.external_id,
        meta_app_id=asset.meta_app_id,
        scopes=list(asset.scopes or []),
        credential_expires_at=asset.credential_expires_at,
        status=asset.status,
    )


@router.get("", response_model=list[ChannelAssetResponse])
async def list_channel_assets(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[ChannelAssetResponse]:
    assets = list(
        (
            await session.scalars(
                select(ChannelAsset)
                .where(ChannelAsset.tenant_id == context.tenant_id)
                .order_by(ChannelAsset.created_at.desc(), ChannelAsset.id.desc())
            )
        ).all()
    )
    return [_asset_response(asset) for asset in assets]


@router.get("/{asset_id}", response_model=ChannelAssetResponse)
async def get_channel_asset(
    asset_id: UUID,
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ChannelAssetResponse:
    asset = await session.scalar(
        select(ChannelAsset).where(ChannelAsset.id == asset_id, ChannelAsset.tenant_id == context.tenant_id)
    )
    if asset is None:
        raise HTTPException(status_code=404, detail={"code": "CHANNEL_ASSET_NOT_FOUND"})
    return _asset_response(asset)


@router.post("/{asset_id}/revalidate", response_model=ChannelAssetResponse)
async def revalidate_asset(
    asset_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> ChannelAssetResponse:
    asset = await revalidate_channel_asset(session, tenant_id=context.tenant_id, asset_id=asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail={"code": "CHANNEL_ASSET_NOT_FOUND"})
    return _asset_response(asset)


@router.delete("/{asset_id}", response_model=ChannelAssetResponse)
async def disconnect_asset(
    asset_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> ChannelAssetResponse:
    asset = await session.scalar(
        select(ChannelAsset)
        .where(ChannelAsset.id == asset_id, ChannelAsset.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail={"code": "CHANNEL_ASSET_NOT_FOUND"})

    await get_credential_store().delete(asset.credential_ref)
    asset.status = "disconnected"
    await write_audit_event(
        session,
        tenant_id=context.tenant_id,
        actor_type="user",
        actor_user_id=context.user_id,
        action="channel_asset.disconnect",
        resource_type="channel_asset",
        resource_id=asset.id,
        metadata={"channel": asset.channel, "external_id": asset.external_id},
    )
    await session.flush()
    return _asset_response(asset)


@router.get("/connect/start", response_model=OAuthStartResponse)
async def start_connection(
    asset_type: MetaAssetType = Query(...),
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> OAuthStartResponse:
    try:
        authorization_url, expires_at, _redirect_uri = await start_meta_oauth(session, context, asset_type)
    except MetaOAuthNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "META_OAUTH_NOT_CONFIGURED"},
        ) from exc
    return OAuthStartResponse(
        authorization_url=authorization_url,
        asset_type=asset_type,
        state_expires_at=expires_at,
    )


@router.get("/connect/callback", response_model=OAuthCallbackResponse)
async def connection_callback(
    state: str | None = Query(default=None, max_length=256),
    code: str | None = Query(default=None, min_length=1, max_length=4096),
    error: str | None = Query(default=None, max_length=120),
    session: AsyncSession = Depends(get_session),
) -> OAuthCallbackResponse:
    if error:
        if not state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "META_OAUTH_CALLBACK_MISSING_PARAMETERS"},
            )
        try:
            oauth_state = await reject_meta_oauth(session, raw_state=state)
        except InvalidOAuthState as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_OAUTH_STATE"},
            ) from exc
        error_code = "META_ACCESS_DENIED" if error == "access_denied" else "META_OAUTH_DENIED"
        return OAuthCallbackResponse(
            onboarding_status="failed",
            asset_type=MetaAssetType(oauth_state.asset_type),
            error_code=error_code,
        )
    if not state or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "META_OAUTH_CALLBACK_MISSING_PARAMETERS"},
        )
    try:
        oauth_state, candidates = await complete_meta_oauth(session, raw_state=state, code=code)
    except MetaOAuthNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "META_OAUTH_NOT_CONFIGURED"},
        ) from exc
    except InvalidOAuthState as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_OAUTH_STATE"},
        ) from exc
    except MetaOAuthError as exc:
        return OAuthCallbackResponse(onboarding_status="failed", error_code="META_OAUTH_FAILED")
    return OAuthCallbackResponse(
        onboarding_status="ready",
        asset_type=MetaAssetType(oauth_state.asset_type),
        assets=[
            DiscoveredMetaAsset(channel=item.channel, external_id=item.external_id, name=item.name)
            for item in candidates
        ],
    )
