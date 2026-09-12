from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, require_tenant_context
from app.core.tenant_context import TenantContext
from app.models.ai import AiProfile
from app.services.ai_models import ModelRegistryError, SUPPORTED_MODELS
from app.services.ai_profiles import save_ai_profile
from app.services.authorization import require_roles
from app.services.audit import write_audit_event


router = APIRouter(prefix="/ai-profile", tags=["ai-profile"])


class AiProfileResponse(BaseModel):
    id: UUID
    version: int
    instructions: str
    service_catalog: dict
    faq: dict
    tone: str
    language: str
    provider: str
    model: str
    active: bool


class AiProfileUpdate(BaseModel):
    instructions: str
    service_catalog: dict = {}
    faq: dict = {}
    tone: str = "professional"
    language: str = "es"
    provider: str
    model: str


@router.get("", response_model=AiProfileResponse)
async def get_active_ai_profile(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AiProfileResponse:
    profile = await session.scalar(select(AiProfile).where(
        AiProfile.tenant_id == context.tenant_id, AiProfile.active.is_(True),
    ).order_by(AiProfile.version.desc()))
    if profile is None:
        raise HTTPException(status_code=404, detail={"code": "AI_PROFILE_NOT_CONFIGURED"})
    return AiProfileResponse.model_validate(profile, from_attributes=True)


@router.put("", response_model=AiProfileResponse)
async def update_ai_profile(
    payload: AiProfileUpdate,
    context: TenantContext = Depends(require_roles("administrador")),
    session: AsyncSession = Depends(get_session),
) -> AiProfileResponse:
    if payload.provider not in SUPPORTED_MODELS or payload.model not in SUPPORTED_MODELS[payload.provider]:
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_AI_MODEL"})
    try:
        profile = await save_ai_profile(session, tenant_id=context.tenant_id, created_by_user_id=context.user_id, **payload.model_dump())
    except ModelRegistryError as exc:
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_AI_MODEL"}) from exc
    await write_audit_event(
        session, tenant_id=context.tenant_id, actor_type="user", actor_user_id=context.user_id,
        action="ai_profile.updated", resource_type="ai_profile", resource_id=profile.id,
        metadata={"version": profile.version},
    )
    return AiProfileResponse.model_validate(profile, from_attributes=True)
