import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import EmailVerificationToken, User


class InvalidVerificationToken(ValueError):
    pass


def hash_verification_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def issue_verification_token(
    session: AsyncSession,
    user_id,
    *,
    lifetime: timedelta = timedelta(hours=24),
) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        EmailVerificationToken(
            user_id=user_id,
            token_hash=hash_verification_token(raw_token),
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    await session.flush()
    return raw_token


async def verify_email_token(session: AsyncSession, raw_token: str) -> User:
    now = datetime.now(UTC)
    token = await session.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == hash_verification_token(raw_token))
        .with_for_update()
    )
    if token is None or token.used_at is not None:
        raise InvalidVerificationToken("INVALID_OR_EXPIRED_TOKEN")
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise InvalidVerificationToken("INVALID_OR_EXPIRED_TOKEN")

    user = await session.scalar(select(User).where(User.id == token.user_id).with_for_update())
    if user is None:
        raise InvalidVerificationToken("INVALID_OR_EXPIRED_TOKEN")
    token.used_at = now
    user.email_verified_at = now
    await session.flush()
    return user

