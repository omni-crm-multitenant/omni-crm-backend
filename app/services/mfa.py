import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_password
from app.models.identity import MfaRecoveryCode, User


class InvalidMfaFactor(ValueError):
    pass


def encrypt_mfa_secret(secret: str) -> str:
    return Fernet(get_settings().mfa_encryption_key.encode()).encrypt(secret.encode()).decode()


def decrypt_mfa_secret(ciphertext: str) -> str:
    try:
        return Fernet(get_settings().mfa_encryption_key.encode()).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise InvalidMfaFactor from exc


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().upper().encode()
    return hmac.new(get_settings().jwt_secret.encode(), normalized, hashlib.sha256).hexdigest()


def _new_recovery_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


async def enroll_mfa(session: AsyncSession, user_id) -> tuple[str, str]:
    user = await session.scalar(select(User).where(User.id == user_id, User.status == "active").with_for_update())
    if user is None or user.mfa_enabled:
        raise InvalidMfaFactor
    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = encrypt_mfa_secret(secret)
    user.mfa_enabled = False
    await session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    return secret, pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Omni CRM")


async def confirm_mfa(session: AsyncSession, user_id, code: str) -> list[str]:
    user = await session.scalar(select(User).where(User.id == user_id, User.status == "active").with_for_update())
    if user is None or user.mfa_enabled or not user.mfa_secret_encrypted:
        raise InvalidMfaFactor
    secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise InvalidMfaFactor
    codes = [_new_recovery_code() for _ in range(10)]
    await session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    session.add_all(
        MfaRecoveryCode(user_id=user.id, code_hash=hash_recovery_code(code_value))
        for code_value in codes
    )
    user.mfa_enabled = True
    await session.flush()
    return codes


async def verify_mfa_factor(session: AsyncSession, user: User, code: str) -> bool:
    if not user.mfa_enabled or not user.mfa_secret_encrypted:
        return False
    secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
    if pyotp.TOTP(secret).verify(code, valid_window=1):
        return True
    recovery = await session.scalar(
        select(MfaRecoveryCode)
        .where(
            MfaRecoveryCode.user_id == user.id,
            MfaRecoveryCode.code_hash == hash_recovery_code(code),
            MfaRecoveryCode.used_at.is_(None),
        )
        .with_for_update()
    )
    if recovery is None:
        return False
    recovery.used_at = datetime.now(UTC)
    return True


async def disable_mfa(session: AsyncSession, user_id, password: str, code: str) -> None:
    user = await session.scalar(select(User).where(User.id == user_id, User.status == "active").with_for_update())
    if user is None or not verify_password(user.password_hash, password):
        raise InvalidMfaFactor
    if not await verify_mfa_factor(session, user, code):
        raise InvalidMfaFactor
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    await session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
