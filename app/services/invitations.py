import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.identity import EmailOutbox, Invitation, Membership, User
from app.services.registration import normalize_email


class InvalidInvitation(ValueError):
    pass


class InvitationConflict(ValueError):
    pass


@dataclass(frozen=True)
class InvitationAcceptance:
    invitation: Invitation
    user: User
    membership: Membership


def hash_invitation_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _expiry_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def create_invitation(
    session: AsyncSession,
    *,
    tenant_id,
    invited_by_user_id,
    email: str,
    role: str,
    lifetime: timedelta = timedelta(days=7),
) -> tuple[Invitation, str]:
    if role not in {"supervisor", "agente_comercial"}:
        raise InvalidInvitation
    normalized_email = normalize_email(email)
    existing_member = await session.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == tenant_id, User.email == normalized_email, Membership.status == "active")
    )
    if existing_member is not None:
        raise InvitationConflict("ALREADY_A_MEMBER")
    existing_pending = list(
        await session.scalars(
            select(Invitation).where(
                Invitation.tenant_id == tenant_id,
                Invitation.email == normalized_email,
                Invitation.status == "pending",
            ).with_for_update()
        )
    )
    for old in existing_pending:
        old.status = "revoked"
    raw_token = secrets.token_urlsafe(32)
    invitation = Invitation(
        tenant_id=tenant_id,
        email=normalized_email,
        role=role,
        token_hash=hash_invitation_token(raw_token),
        invited_by_user_id=invited_by_user_id,
        expires_at=datetime.now(UTC) + lifetime,
    )
    session.add(invitation)
    await session.flush()
    base_url = str(get_settings().auth_public_base_url).rstrip("/")
    accept_url = f"{base_url}/invitations/{raw_token}"
    session.add(
        EmailOutbox(
            tenant_id=tenant_id,
            recipient=normalized_email,
            template="invitation",
            subject="Te invitaron a Omni CRM",
            text_body=f"Acepta tu invitación: {accept_url}",
            html_body=f'<p><a href="{accept_url}">Aceptar invitación</a></p>',
            payload={"invitation_id": str(invitation.id)},
        )
    )
    return invitation, raw_token


async def get_pending_invitation(session: AsyncSession, raw_token: str, *, lock: bool = False) -> Invitation:
    statement = select(Invitation).where(Invitation.token_hash == hash_invitation_token(raw_token))
    if lock:
        statement = statement.with_for_update()
    invitation = await session.scalar(statement)
    if invitation is None or invitation.status != "pending":
        raise InvalidInvitation
    if _expiry_utc(invitation.expires_at) <= datetime.now(UTC):
        invitation.status = "expired"
        raise InvalidInvitation
    return invitation


async def accept_invitation(
    session: AsyncSession,
    *,
    raw_token: str,
    name: str | None,
    password: str | None,
) -> InvitationAcceptance:
    invitation = await get_pending_invitation(session, raw_token, lock=True)
    user = await session.scalar(select(User).where(User.email == invitation.email).with_for_update())
    if user is None:
        if not name or not password or len(password) < 12:
            raise InvalidInvitation("INVITEE_DETAILS_REQUIRED")
        user = User(
            name=name.strip(),
            email=invitation.email,
            password_hash=hash_password(password),
            email_verified_at=datetime.now(UTC),
            status="active",
        )
        session.add(user)
        await session.flush()
    membership = await session.scalar(
        select(Membership).where(
            Membership.tenant_id == invitation.tenant_id,
            Membership.user_id == user.id,
        ).with_for_update()
    )
    if membership is None:
        membership = Membership(
            tenant_id=invitation.tenant_id,
            user_id=user.id,
            role=invitation.role,
            status="active",
            accepted_at=datetime.now(UTC),
        )
        session.add(membership)
    elif membership.status == "active":
        raise InvitationConflict("ALREADY_A_MEMBER")
    else:
        membership.role = invitation.role
        membership.status = "active"
        membership.accepted_at = datetime.now(UTC)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    invitation.status = "accepted"
    await session.flush()
    return InvitationAcceptance(invitation, user, membership)


async def revoke_invitation(session: AsyncSession, *, invitation_id, tenant_id) -> Invitation:
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.tenant_id == tenant_id,
        ).with_for_update()
    )
    if invitation is None or invitation.status != "pending":
        raise InvalidInvitation
    invitation.status = "revoked"
    return invitation
