from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tokens import TokenClaims, issue_token
from app.models.identity import AuthSession, Membership, RefreshToken, User


class InvalidSession(ValueError):
    pass


class RefreshReplay(InvalidSession):
    pass


@dataclass(frozen=True)
class SessionPair:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    tenant_id: UUID
    membership_id: UUID
    session_id: UUID


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _new_refresh(session_id: UUID, family_id: UUID, expires_at: datetime, parent_id: UUID | None = None):
    secret = secrets.token_urlsafe(48)
    token = RefreshToken(
        session_id=session_id,
        family_id=family_id,
        parent_id=parent_id,
        secret_hash=_hash_secret(secret),
        expires_at=expires_at,
    )
    return token, secret


def _serialize_refresh(token: RefreshToken, secret: str) -> str:
    return f"rt.{token.id}.{secret}"


def _parse_refresh(raw_token: str) -> tuple[UUID, str]:
    try:
        prefix, token_id, secret = raw_token.split(".", 2)
        if prefix != "rt" or len(secret) < 32:
            raise ValueError
        return UUID(token_id), secret
    except (ValueError, AttributeError) as exc:
        raise InvalidSession("invalid refresh token") from exc


def _access_for(auth_session: AuthSession) -> str:
    settings = get_settings()
    return issue_token(
        user_id=auth_session.user_id,
        purpose="access",
        ttl_seconds=settings.access_token_ttl_seconds,
        session_id=auth_session.id,
        tenant_id=auth_session.tenant_id,
        membership_id=auth_session.membership_id,
    )


async def issue_session_pair(
    db: AsyncSession,
    *,
    user_id: UUID,
    membership: Membership,
) -> SessionPair:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
    auth_session = AuthSession(
        user_id=user_id,
        membership_id=membership.id,
        tenant_id=membership.tenant_id,
        expires_at=expires_at,
    )
    db.add(auth_session)
    await db.flush()
    refresh, secret = _new_refresh(auth_session.id, uuid4(), expires_at)
    db.add(refresh)
    await db.flush()
    return SessionPair(
        access_token=_access_for(auth_session),
        refresh_token=_serialize_refresh(refresh, secret),
        token_type="bearer",
        expires_in=settings.access_token_ttl_seconds,
        tenant_id=auth_session.tenant_id,
        membership_id=auth_session.membership_id,
        session_id=auth_session.id,
    )


async def validate_access_session(db: AsyncSession, claims: TokenClaims) -> AuthSession:
    if not all((claims.session_id, claims.tenant_id, claims.membership_id)):
        raise InvalidSession("incomplete access token")
    statement = (
        select(AuthSession)
        .join(User, User.id == AuthSession.user_id)
        .join(Membership, Membership.id == AuthSession.membership_id)
        .where(
            AuthSession.id == claims.session_id,
            AuthSession.user_id == claims.subject,
            AuthSession.tenant_id == claims.tenant_id,
            AuthSession.membership_id == claims.membership_id,
            AuthSession.status == "active",
            User.status == "active",
            Membership.status == "active",
            Membership.user_id == AuthSession.user_id,
            Membership.tenant_id == AuthSession.tenant_id,
        )
    )
    auth_session = await db.scalar(statement)
    if auth_session is None or _as_utc(auth_session.expires_at) <= datetime.now(UTC):
        raise InvalidSession("inactive session")
    return auth_session


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> SessionPair:
    token_id, secret = _parse_refresh(raw_token)
    replayed = False
    result: SessionPair | None = None
    async with db.begin():
        refresh = await db.scalar(
            select(RefreshToken).where(RefreshToken.id == token_id).with_for_update()
        )
        if refresh is None or not hmac.compare_digest(refresh.secret_hash, _hash_secret(secret)):
            raise InvalidSession("invalid refresh token")
        auth_session = await db.get(AuthSession, refresh.session_id)
        if refresh.consumed_at is not None:
            replayed = True
            now = datetime.now(UTC)
            auth_session.status = "revoked"
            auth_session.revoked_at = now
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == refresh.family_id)
                .values(revoked_at=now)
            )
        else:
            now = datetime.now(UTC)
            if refresh.revoked_at is not None or _as_utc(refresh.expires_at) <= now:
                raise InvalidSession("inactive refresh token")
            if auth_session is None:
                raise InvalidSession("missing session")
            claims = TokenClaims(
                subject=auth_session.user_id,
                purpose="access",
                expires_at=0,
                jwt_id=uuid4(),
                session_id=auth_session.id,
                tenant_id=auth_session.tenant_id,
                membership_id=auth_session.membership_id,
            )
            await validate_access_session(db, claims)
            refresh.consumed_at = now
            replacement, replacement_secret = _new_refresh(
                auth_session.id,
                refresh.family_id,
                min(_as_utc(auth_session.expires_at), now + timedelta(days=get_settings().refresh_token_ttl_days)),
                parent_id=refresh.id,
            )
            db.add(replacement)
            await db.flush()
            result = SessionPair(
                access_token=_access_for(auth_session),
                refresh_token=_serialize_refresh(replacement, replacement_secret),
                token_type="bearer",
                expires_in=get_settings().access_token_ttl_seconds,
                tenant_id=auth_session.tenant_id,
                membership_id=auth_session.membership_id,
                session_id=auth_session.id,
            )
    if replayed:
        raise RefreshReplay("refresh token replay")
    assert result is not None
    return result


async def revoke_session(db: AsyncSession, session_id: UUID, *, user_id: UUID) -> None:
    now = datetime.now(UTC)
    auth_session = await db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
        ).with_for_update()
    )
    if auth_session is None:
        return
    auth_session.status = "revoked"
    auth_session.revoked_at = now
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == auth_session.id)
        .values(revoked_at=now)
    )


async def revoke_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    now = datetime.now(UTC)
    session_ids = select(AuthSession.id).where(AuthSession.user_id == user_id)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id)
        .values(status="revoked", revoked_at=now)
    )
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id.in_(session_ids))
        .values(revoked_at=now)
    )
