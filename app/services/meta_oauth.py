from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.tenant_context import TenantContext
from app.models.identity import MetaOAuthState
from app.repositories.channel_assets import upsert_meta_assets
from app.services.credentials import CredentialStore, get_credential_store
from app.services.egress import hardened_http_client


class MetaAssetType(StrEnum):
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"
    AD_ACCOUNT = "ad_account"


SCOPES_BY_ASSET: dict[MetaAssetType, tuple[str, ...]] = {
    MetaAssetType.WHATSAPP: (
        "business_management",
        "whatsapp_business_management",
        "whatsapp_business_messaging",
    ),
    MetaAssetType.MESSENGER: (
        "business_management",
        "pages_manage_metadata",
        "pages_read_engagement",
        "pages_show_list",
    ),
    MetaAssetType.INSTAGRAM: (
        "business_management",
        "instagram_basic",
        "instagram_manage_messages",
        "pages_manage_metadata",
        "pages_read_engagement",
        "pages_show_list",
    ),
    MetaAssetType.AD_ACCOUNT: ("ads_read", "business_management"),
}


class MetaOAuthNotConfigured(RuntimeError):
    pass


class MetaOAuthError(RuntimeError):
    pass


class InvalidOAuthState(MetaOAuthError):
    pass


@dataclass(frozen=True)
class MetaAssetCandidate:
    channel: MetaAssetType
    external_id: str
    name: str | None
    credential: str
    scopes: tuple[str, ...]
    credential_expires_at: datetime | None = None


class MetaGraphClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"https://graph.facebook.com/{settings.meta_graph_api_version}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> tuple[str, datetime | None]:
        if not self.settings.meta_app_id or not self.settings.meta_app_secret:
            raise MetaOAuthNotConfigured("Meta OAuth credentials are not configured")
        params = {
            "client_id": self.settings.meta_app_id,
            "client_secret": self.settings.meta_app_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        payload = await self._get("/oauth/access_token", params=params)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise MetaOAuthError("Meta token response has no access token")
        expires_in = payload.get("expires_in")
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=int(expires_in))
            if isinstance(expires_in, (int, float)) and expires_in > 0
            else None
        )
        return token, expires_at

    async def get(self, path: str, *, access_token: str, params: dict[str, str]) -> dict:
        return await self._get(path, params={**params, "access_token": access_token})

    async def debug_token(self, token: str) -> dict:
        if not self.settings.meta_app_id or not self.settings.meta_app_secret:
            raise MetaOAuthNotConfigured("Meta OAuth credentials are not configured")
        return await self._get(
            "/debug_token",
            params={
                "input_token": token,
                "access_token": f"{self.settings.meta_app_id}|{self.settings.meta_app_secret}",
            },
        )

    async def _get(self, path: str, *, params: dict[str, str]) -> dict:
        try:
            async with hardened_http_client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
        except httpx.HTTPError as exc:
            raise MetaOAuthError("Meta request failed") from exc
        if response.status_code >= 400:
            raise MetaOAuthError("Meta rejected OAuth request")
        try:
            payload = response.json()
        except ValueError as exc:
            raise MetaOAuthError("Meta returned invalid JSON") from exc
        if not isinstance(payload, dict) or "error" in payload:
            raise MetaOAuthError("Meta returned an OAuth error")
        return payload


def oauth_redirect_uri(settings: Settings) -> str:
    if settings.meta_oauth_redirect_uri is not None:
        return str(settings.meta_oauth_redirect_uri).rstrip("/")
    return f"{str(settings.app_base_url).rstrip('/')}/api/v1/channel-assets/connect/callback"


def _state_hash(raw_state: str) -> str:
    return hashlib.sha256(raw_state.encode("ascii")).hexdigest()


async def create_oauth_state(
    session: AsyncSession,
    context: TenantContext,
    asset_type: MetaAssetType,
    redirect_uri: str,
    *,
    ttl_seconds: int = 600,
) -> tuple[str, datetime]:
    raw_state = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    session.add(
        MetaOAuthState(
            state_hash=_state_hash(raw_state),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            asset_type=asset_type.value,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return raw_state, expires_at


async def consume_oauth_state(session: AsyncSession, raw_state: str) -> MetaOAuthState:
    state = await session.scalar(
        select(MetaOAuthState)
        .where(MetaOAuthState.state_hash == _state_hash(raw_state))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if state is None or state.used_at is not None or state.expires_at.replace(tzinfo=UTC) <= now:
        raise InvalidOAuthState("Invalid or expired OAuth state")
    state.used_at = now
    await session.flush()
    return state


async def reject_meta_oauth(session: AsyncSession, *, raw_state: str) -> MetaOAuthState:
    """Consume denied OAuth state so Meta cannot replay it."""
    state = await consume_oauth_state(session, raw_state)
    await session.commit()
    return state


def build_authorization_url(
    settings: Settings,
    *,
    asset_type: MetaAssetType,
    state: str,
    redirect_uri: str,
) -> str:
    if not settings.meta_app_id:
        raise MetaOAuthNotConfigured("META_APP_ID is not configured")
    query = urlencode(
        {
            "client_id": settings.meta_app_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code",
            "scope": ",".join(SCOPES_BY_ASSET[asset_type]),
        }
    )
    return f"https://www.facebook.com/{settings.meta_graph_api_version}/dialog/oauth?{query}"


async def start_meta_oauth(
    session: AsyncSession,
    context: TenantContext,
    asset_type: MetaAssetType,
) -> tuple[str, datetime, str]:
    settings = get_settings()
    if not settings.meta_app_id:
        raise MetaOAuthNotConfigured("META_APP_ID is not configured")
    redirect_uri = oauth_redirect_uri(settings)
    raw_state, expires_at = await create_oauth_state(session, context, asset_type, redirect_uri)
    return build_authorization_url(
        settings,
        asset_type=asset_type,
        state=raw_state,
        redirect_uri=redirect_uri,
    ), expires_at, redirect_uri


async def discover_meta_assets(
    client: MetaGraphClient,
    *,
    asset_type: MetaAssetType,
    access_token: str,
    credential_expires_at: datetime | None,
) -> list[MetaAssetCandidate]:
    scopes = SCOPES_BY_ASSET[asset_type]
    if asset_type in {MetaAssetType.MESSENGER, MetaAssetType.INSTAGRAM}:
        payload = await client.get(
            "/me/accounts",
            access_token=access_token,
            params={"fields": "id,name,access_token,instagram_business_account{id,username}"},
        )
        candidates: list[MetaAssetCandidate] = []
        for page in payload.get("data", []):
            if not isinstance(page, dict) or not page.get("id"):
                continue
            page_token = page.get("access_token")
            if not isinstance(page_token, str) or not page_token:
                continue
            if asset_type is MetaAssetType.MESSENGER:
                candidates.append(
                    MetaAssetCandidate(
                        channel=asset_type,
                        external_id=str(page["id"]),
                        name=page.get("name"),
                        credential=page_token,
                        scopes=scopes,
                        credential_expires_at=credential_expires_at,
                    )
                )
                continue
            instagram = page.get("instagram_business_account")
            if isinstance(instagram, dict) and instagram.get("id"):
                candidates.append(
                    MetaAssetCandidate(
                        channel=asset_type,
                        external_id=str(instagram["id"]),
                        name=instagram.get("username") or page.get("name"),
                        credential=page_token,
                        scopes=scopes,
                        credential_expires_at=credential_expires_at,
                    )
                )
        return candidates

    if asset_type is MetaAssetType.AD_ACCOUNT:
        payload = await client.get(
            "/me/adaccounts",
            access_token=access_token,
            params={"fields": "id,name,account_status"},
        )
        return [
            MetaAssetCandidate(
                channel=asset_type,
                external_id=str(item["id"]),
                name=item.get("name"),
                credential=access_token,
                scopes=scopes,
                credential_expires_at=credential_expires_at,
            )
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]

    businesses = await client.get(
        "/me/businesses",
        access_token=access_token,
        params={"fields": "id,name"},
    )
    candidates = []
    for business in businesses.get("data", []):
        if not isinstance(business, dict) or not business.get("id"):
            continue
        wabas = await client.get(
            f"/{business['id']}/owned_whatsapp_business_accounts",
            access_token=access_token,
            params={"fields": "id,name"},
        )
        for waba in wabas.get("data", []):
            if not isinstance(waba, dict) or not waba.get("id"):
                continue
            phones = await client.get(
                f"/{waba['id']}/phone_numbers",
                access_token=access_token,
                params={"fields": "id,display_phone_number,verified_name"},
            )
            for phone in phones.get("data", []):
                if not isinstance(phone, dict) or not phone.get("id"):
                    continue
                candidates.append(
                    MetaAssetCandidate(
                        channel=asset_type,
                        external_id=str(phone["id"]),
                        name=phone.get("verified_name") or phone.get("display_phone_number") or waba.get("name"),
                        credential=access_token,
                        scopes=scopes,
                        credential_expires_at=credential_expires_at,
                    )
                )
    return candidates


async def complete_meta_oauth(
    session: AsyncSession,
    *,
    raw_state: str,
    code: str,
    credential_store: CredentialStore | None = None,
) -> tuple[MetaOAuthState, list[MetaAssetCandidate]]:
    settings = get_settings()
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise MetaOAuthNotConfigured("Meta OAuth credentials are not configured")
    state = await consume_oauth_state(session, raw_state)
    # Commit state consumption before remote calls. A failed remote call cannot replay OAuth state.
    await session.commit()
    client = MetaGraphClient(settings)
    access_token, expires_at = await client.exchange_code(code=code, redirect_uri=state.redirect_uri)
    candidates = await discover_meta_assets(
        client,
        asset_type=MetaAssetType(state.asset_type),
        access_token=access_token,
        credential_expires_at=expires_at,
    )
    await upsert_meta_assets(
        session,
        tenant_id=state.tenant_id,
        meta_app_id=settings.meta_app_id,
        candidates=candidates,
        credential_store=credential_store or get_credential_store(),
    )
    return state, candidates
