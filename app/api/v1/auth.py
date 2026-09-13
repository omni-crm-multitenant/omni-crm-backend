import re
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentIdentity, bearer_scheme, get_session, require_current_identity
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.core.tokens import InvalidToken, decode_token, issue_token
from app.models.identity import EmailOutbox, Tenant, User
from app.repositories.memberships import get_membership, list_memberships
from app.services.email_verification import InvalidVerificationToken, verify_email_token
from app.services.registration import (
    EmailAlreadyRegisteredError,
    RegistrationResult,
    normalize_email,
    register_company,
)
from app.services.sessions import (
    InvalidSession,
    RefreshReplay,
    SessionPair,
    issue_session_pair,
    revoke_session,
    rotate_refresh_token,
    validate_access_session,
)
from app.services.password_reset import (
    InvalidPasswordResetToken,
    issue_password_reset_token,
    reset_password as apply_password_reset,
)
from app.services.mfa import InvalidMfaFactor, confirm_mfa, disable_mfa, enroll_mfa, verify_mfa_factor
from app.services.onboarding import evaluate_onboarding


router = APIRouter(prefix="/auth", tags=["auth"])


class RegistrationRequest(BaseModel):
    admin_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=256)
    company_name: str = Field(min_length=2, max_length=255)

    @field_validator("admin_name", "company_name")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("must contain at least two visible characters")
        return stripped

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email")
        return normalized


class RegisteredUser(BaseModel):
    id: UUID
    name: str
    email: str


class RegisteredTenant(BaseModel):
    id: UUID
    name: str
    slug: str


class RegistrationResponse(BaseModel):
    user: RegisteredUser
    tenant: RegisteredTenant
    onboarding_status: str = "in_progress"


class VerificationResponse(BaseModel):
    status: str


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return normalize_email(value)


class MembershipChoice(BaseModel):
    membership_id: UUID
    tenant_id: UUID
    tenant_name: str
    role: str


class LoginResponse(BaseModel):
    next_step: Literal["authenticated", "mfa_required", "tenant_selection"]
    challenge_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
    tenant_id: UUID | None = None
    membership_id: UUID | None = None
    session_id: UUID | None = None


class SelectTenantRequest(BaseModel):
    tenant_id: UUID


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=512)


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    tenant_id: UUID
    membership_id: UUID
    session_id: UUID


class LogoutResponse(BaseModel):
    status: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_forgot_email(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class NeutralResponse(BaseModel):
    status: str


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class MfaConfirmResponse(BaseModel):
    status: str
    recovery_codes: list[str]


class MfaDisableRequest(MfaCodeRequest):
    password: str = Field(min_length=1, max_length=256)


class MfaVerifyRequest(MfaCodeRequest):
    challenge_token: str = Field(min_length=32, max_length=2048)


DUMMY_PASSWORD_HASH = hash_password("dummy-password-used-only-for-timing")


def session_response(pair: SessionPair) -> SessionResponse:
    return SessionResponse(**pair.__dict__)


def login_session_response(pair: SessionPair) -> LoginResponse:
    return LoginResponse(next_step="authenticated", **pair.__dict__)


async def add_verification_intent(
    session: AsyncSession,
    result: RegistrationResult,
) -> None:
    session.add(
        EmailOutbox(
            tenant_id=result.tenant.id,
            user_id=result.user.id,
            recipient=result.user.email,
            template="verify_email",
            subject="Verifica tu cuenta de Omni",
            text_body="Tu registro fue recibido. El enlace de verificación se generará de forma segura.",
            payload={
                "tenant_id": str(result.tenant.id),
                "user_id": str(result.user.id),
            },
        )
    )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegistrationRequest,
    session: AsyncSession = Depends(get_session),
) -> RegistrationResponse:
    try:
        result = await register_company(
            session,
            company_name=payload.company_name,
            admin_name=payload.admin_name,
            admin_email=payload.email,
            admin_password=payload.password,
            after_identity_created=add_verification_intent,
        )
    except (EmailAlreadyRegisteredError, IntegrityError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "EMAIL_ALREADY_REGISTERED"},
        ) from exc

    onboarding = await evaluate_onboarding(session, result.tenant.id)

    return RegistrationResponse(
        user=RegisteredUser(id=result.user.id, name=result.user.name, email=result.user.email),
        tenant=RegisteredTenant(
            id=result.tenant.id,
            name=result.tenant.name,
            slug=result.tenant.slug,
        ),
        onboarding_status=onboarding.status,
    )


@router.get("/verify-email", response_model=VerificationResponse)
async def verify_email(
    token: str = Query(min_length=32, max_length=256),
    session: AsyncSession = Depends(get_session),
) -> VerificationResponse:
    try:
        async with session.begin():
            await verify_email_token(session, token)
    except InvalidVerificationToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_OR_EXPIRED_TOKEN"},
        ) from exc
    return VerificationResponse(status="verified")


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    user = await session.scalar(select(User).where(User.email == payload.email, User.status == "active"))
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    if not verify_password(password_hash, payload.password) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS"},
        )
    user.last_login_at = datetime.now(UTC)
    settings = get_settings()
    if user.mfa_enabled:
        return LoginResponse(
            next_step="mfa_required",
            challenge_token=issue_token(
                user_id=user.id,
                purpose="mfa_challenge",
                ttl_seconds=settings.challenge_token_ttl_seconds,
            ),
        )

    memberships = await list_memberships(session, user_id=user.id, active_only=True)
    if not memberships:
        raise HTTPException(status_code=403, detail={"code": "NO_ACTIVE_MEMBERSHIP"})
    if len(memberships) > 1:
        return LoginResponse(
            next_step="tenant_selection",
            challenge_token=issue_token(
                user_id=user.id,
                purpose="tenant_selection",
                ttl_seconds=settings.challenge_token_ttl_seconds,
            ),
        )
    return login_session_response(await issue_session_pair(session, user_id=user.id, membership=memberships[0]))


async def _claims_from_selection_or_access(
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidToken("missing token")
    claims = decode_token(credentials.credentials)
    if claims.purpose == "access":
        await validate_access_session(session, claims)
    elif claims.purpose != "tenant_selection":
        raise InvalidToken("invalid purpose")
    return claims


@router.get("/memberships", response_model=list[MembershipChoice])
async def memberships_for_login(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> list[MembershipChoice]:
    try:
        claims = await _claims_from_selection_or_access(credentials, session)
    except (InvalidToken, InvalidSession) as exc:
        raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_REQUIRED"}) from exc
    memberships = await list_memberships(session, user_id=claims.subject, active_only=True)
    tenant_names: dict[UUID, str] = {
        row[0]: row[1]
        for row in (await session.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_([m.tenant_id for m in memberships])))).all()
    } if memberships else {}
    return [
        MembershipChoice(
            membership_id=membership.id,
            tenant_id=membership.tenant_id,
            tenant_name=tenant_names[membership.tenant_id],
            role=membership.role,
        )
        for membership in memberships
    ]


@router.post("/select-tenant", response_model=SessionResponse)
async def select_tenant(
    payload: SelectTenantRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    try:
        claims = await _claims_from_selection_or_access(credentials, session)
        membership = await get_membership(
            session,
            user_id=claims.subject,
            tenant_id=payload.tenant_id,
            active_only=True,
        )
        if membership is None:
            raise InvalidSession("inactive membership")
        return session_response(await issue_session_pair(session, user_id=claims.subject, membership=membership))
    except (InvalidToken, InvalidSession) as exc:
        raise HTTPException(status_code=401, detail={"code": "TENANT_SELECTION_DENIED"}) from exc


@router.post("/refresh", response_model=SessionResponse)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_session)) -> SessionResponse:
    try:
        return session_response(await rotate_refresh_token(session, payload.refresh_token))
    except RefreshReplay as exc:
        raise HTTPException(status_code=401, detail={"code": "REFRESH_REPLAY_DETECTED"}) from exc
    except InvalidSession as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_REFRESH_TOKEN"}) from exc


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    identity: CurrentIdentity = Depends(require_current_identity),
    session: AsyncSession = Depends(get_session),
) -> LogoutResponse:
    assert identity.session_id is not None
    await revoke_session(session, identity.session_id, user_id=identity.user_id)
    return LogoutResponse(status="revoked")


@router.post("/forgot-password", response_model=NeutralResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> NeutralResponse:
    user = await session.scalar(select(User).where(User.email == payload.email, User.status == "active"))
    if user is not None:
        raw_token = await issue_password_reset_token(session, user.id)
        base_url = str(get_settings().auth_public_base_url).rstrip("/")
        reset_url = f"{base_url}/reset-password?token={raw_token}"
        session.add(
            EmailOutbox(
                user_id=user.id,
                recipient=user.email,
                template="reset_password",
                subject="Restablece tu contraseña de Omni",
                text_body=f"Restablece tu contraseña: {reset_url}",
                html_body=f'<p><a href="{reset_url}">Restablecer contraseña</a></p>',
                payload={"user_id": str(user.id)},
            )
        )
    return NeutralResponse(status="accepted")


@router.post("/reset-password", response_model=NeutralResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> NeutralResponse:
    try:
        await apply_password_reset(session, payload.token, payload.new_password)
    except InvalidPasswordResetToken as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_OR_EXPIRED_TOKEN"},
        ) from exc
    return NeutralResponse(status="password_updated")


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    identity: CurrentIdentity = Depends(require_current_identity),
    session: AsyncSession = Depends(get_session),
) -> MfaEnrollResponse:
    secret, provisioning_uri = await enroll_mfa(session, identity.user_id)
    return MfaEnrollResponse(secret=secret, provisioning_uri=provisioning_uri)


@router.post("/mfa/confirm", response_model=MfaConfirmResponse)
async def mfa_confirm(
    payload: MfaCodeRequest,
    identity: CurrentIdentity = Depends(require_current_identity),
    session: AsyncSession = Depends(get_session),
) -> MfaConfirmResponse:
    try:
        codes = await confirm_mfa(session, identity.user_id, payload.code)
    except InvalidMfaFactor as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_MFA_FACTOR"}) from exc
    return MfaConfirmResponse(status="enabled", recovery_codes=codes)


@router.post("/mfa/disable", response_model=NeutralResponse)
async def mfa_disable(
    payload: MfaDisableRequest,
    identity: CurrentIdentity = Depends(require_current_identity),
    session: AsyncSession = Depends(get_session),
) -> NeutralResponse:
    try:
        await disable_mfa(session, identity.user_id, payload.password, payload.code)
    except InvalidMfaFactor as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_MFA_FACTOR"}) from exc
    return NeutralResponse(status="disabled")


@router.post("/mfa/verify", response_model=LoginResponse)
async def mfa_verify(
    payload: MfaVerifyRequest,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    try:
        claims = decode_token(payload.challenge_token, expected_purpose="mfa_challenge")
        user = await session.scalar(select(User).where(User.id == claims.subject, User.status == "active").with_for_update())
        if user is None or not await verify_mfa_factor(session, user, payload.code):
            raise InvalidMfaFactor
        memberships = await list_memberships(session, user_id=user.id, active_only=True)
        if not memberships:
            raise InvalidMfaFactor
        if len(memberships) > 1:
            return LoginResponse(
                next_step="tenant_selection",
                challenge_token=issue_token(
                    user_id=user.id,
                    purpose="tenant_selection",
                    ttl_seconds=get_settings().challenge_token_ttl_seconds,
                ),
            )
        return login_session_response(await issue_session_pair(session, user_id=user.id, membership=memberships[0]))
    except (InvalidToken, InvalidMfaFactor) as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_MFA_FACTOR"}) from exc
