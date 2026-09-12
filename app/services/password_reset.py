import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import PasswordResetToken, User
from app.services.sessions import revoke_all_user_sessions


class InvalidPasswordResetToken(ValueError):
    pass


def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def issue_password_reset_token(
    session: AsyncSession,
    user_id,
    *,
    lifetime: timedelta = timedelta(minutes=30),
) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            user_id=user_id,
            token_hash=hash_reset_token(raw_token),
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    await session.flush()
    return raw_token


async def reset_password(session: AsyncSession, raw_token: str, new_password: str) -> User:
    now = datetime.now(UTC)
    token = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_reset_token(raw_token))
        .with_for_update()
    )
    if token is None or token.used_at is not None:
        raise InvalidPasswordResetToken
    expires_at = token.expires_at.replace(tzinfo=UTC) if token.expires_at.tzinfo is None else token.expires_at
    if expires_at <= now:
        raise InvalidPasswordResetToken
    user = await session.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user is None or user.status != "active":
        raise InvalidPasswordResetToken
    user.password_hash = hash_password(new_password)
    token.used_at = now
    await revoke_all_user_sessions(session, user.id)
    await session.flush()
    return user
