import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.tenant_context import TenantContext
from app.api.dependencies import require_roles
from app.services.invitations import (
    InvalidInvitation,
    InvitationConflict,
    accept_invitation,
    create_invitation,
    get_pending_invitation,
    revoke_invitation,
)
from app.services.registration import normalize_email


router = APIRouter(tags=["invitations"])


class CreateInvitationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    role: Literal["supervisor", "agente_comercial"]

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email")
        return normalized


class InvitationResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=256)


class AcceptedInvitationResponse(BaseModel):
    status: str
    user_id: UUID
    membership_id: UUID
    tenant_id: UUID
    role: str


def invitation_response(invitation) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
    )


@router.post(
    "/tenants/{tenant_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    tenant_id: UUID,
    payload: CreateInvitationRequest,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> InvitationResponse:
    if tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "CROSS_TENANT_ACCESS_DENIED"})
    try:
        invitation, _raw_token = await create_invitation(
            session,
            tenant_id=context.tenant_id,
            invited_by_user_id=context.user_id,
            email=payload.email,
            role=payload.role,
        )
    except InvitationConflict as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return invitation_response(invitation)


@router.get("/invitations/{token}", response_model=InvitationResponse)
async def invitation_details(token: str, session: AsyncSession = Depends(get_session)) -> InvitationResponse:
    try:
        return invitation_response(await get_pending_invitation(session, token))
    except InvalidInvitation as exc:
        raise HTTPException(status_code=404, detail={"code": "INVITATION_NOT_AVAILABLE"}) from exc


@router.post("/invitations/{token}/accept", response_model=AcceptedInvitationResponse)
async def accept_user_invitation(
    token: str,
    payload: AcceptInvitationRequest,
    session: AsyncSession = Depends(get_session),
) -> AcceptedInvitationResponse:
    try:
        result = await accept_invitation(
            session,
            raw_token=token,
            name=payload.name,
            password=payload.password,
        )
    except InvalidInvitation as exc:
        code = str(exc) if str(exc) else "INVITATION_NOT_AVAILABLE"
        raise HTTPException(status_code=400, detail={"code": code}) from exc
    except InvitationConflict as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
    return AcceptedInvitationResponse(
        status="accepted",
        user_id=result.user.id,
        membership_id=result.membership.id,
        tenant_id=result.membership.tenant_id,
        role=result.membership.role,
    )


@router.delete("/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
async def revoke_user_invitation(
    tenant_id: UUID,
    invitation_id: UUID,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> None:
    if tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail={"code": "CROSS_TENANT_ACCESS_DENIED"})
    try:
        await revoke_invitation(session, invitation_id=invitation_id, tenant_id=context.tenant_id)
    except InvalidInvitation as exc:
        raise HTTPException(status_code=404, detail={"code": "INVITATION_NOT_AVAILABLE"}) from exc
