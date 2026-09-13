from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.identity import Membership, User
from app.core.tenant_context import TenantContext, set_current_tenant_id
from app.core.tokens import InvalidToken, decode_token
from app.services.sessions import InvalidSession, validate_access_session
from app.core.request_context import actor_id_var


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentIdentity:
    user_id: UUID
    tenant_id: UUID | None = None
    membership_id: UUID | None = None
    session_id: UUID | None = None


async def require_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentIdentity:
    try:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise InvalidToken("missing access token")
        claims = decode_token(credentials.credentials, expected_purpose="access")
        auth_session = await validate_access_session(session, claims)
        return CurrentIdentity(
            user_id=auth_session.user_id,
            tenant_id=auth_session.tenant_id,
            membership_id=auth_session.membership_id,
            session_id=auth_session.id,
        )
    except (InvalidToken, InvalidSession) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED"},
        ) from exc


async def require_verified_identity(
    identity: CurrentIdentity = Depends(require_current_identity),
    session: AsyncSession = Depends(get_session),
) -> CurrentIdentity:
    verified_at = await session.scalar(
        select(User.email_verified_at).where(
            User.id == identity.user_id,
            User.status == "active",
        )
    )
    if verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "EMAIL_NOT_VERIFIED"},
        )
    return identity


async def require_tenant_context(
    identity: CurrentIdentity = Depends(require_verified_identity),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    if identity.tenant_id is None or identity.membership_id is None:
        raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_REQUIRED"})
    membership = await session.scalar(
        select(Membership).where(
            Membership.id == identity.membership_id,
            Membership.user_id == identity.user_id,
            Membership.tenant_id == identity.tenant_id,
            Membership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail={"code": "MEMBERSHIP_INACTIVE"})
    actor_id_var.set(membership.user_id)
    set_current_tenant_id(membership.tenant_id)
    return TenantContext(
        tenant_id=membership.tenant_id,
        membership_id=membership.id,
        user_id=membership.user_id,
        role=cast(Role, membership.role),
    )

Role = Literal["administrador", "supervisor", "agente_comercial"]


def require_roles(*allowed_roles: Role):
    allowed = frozenset(allowed_roles)

    async def dependency(context: TenantContext = Depends(require_tenant_context)) -> TenantContext:
        if context.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ROLE_FORBIDDEN"},
            )
        return context

    return dependency


async def require_supervisor_or_admin(
    context: TenantContext = Depends(require_tenant_context),
) -> TenantContext:
    if context.role not in {"administrador", "supervisor"}:
        raise HTTPException(status_code=403, detail={"code": "ROLE_FORBIDDEN"})
    return context


__all__ = [
    "CurrentIdentity",
    "get_session",
    "require_current_identity",
    "require_tenant_context",
    "require_verified_identity",
]
