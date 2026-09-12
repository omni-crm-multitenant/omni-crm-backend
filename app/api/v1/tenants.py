from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentIdentity, get_session, require_tenant_context, require_verified_identity
from app.api.v1.auth import RegisteredTenant
from app.core.tenant_context import TenantContext
from app.services.onboarding import evaluate_onboarding
from app.services.registration import create_tenant_for_existing_user


router = APIRouter(prefix="/tenants", tags=["tenants"])


class CreateTenantRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)

    @field_validator("company_name")
    @classmethod
    def strip_company_name(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("must contain at least two visible characters")
        return stripped


class OnboardingStepResponse(BaseModel):
    key: str
    status: str
    reason_code: str | None = None
    blocking: bool


class OnboardingResponse(BaseModel):
    status: str
    steps: list[OnboardingStepResponse]


@router.post("", response_model=RegisteredTenant, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: CreateTenantRequest,
    identity: CurrentIdentity = Depends(require_verified_identity),
    session: AsyncSession = Depends(get_session),
) -> RegisteredTenant:
    try:
        tenant, _membership = await create_tenant_for_existing_user(
            session,
            user_id=identity.user_id,
            company_name=payload.company_name,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED"},
        ) from exc
    return RegisteredTenant(id=tenant.id, name=tenant.name, slug=tenant.slug)


@router.get("/onboarding", response_model=OnboardingResponse)
async def onboarding_status(
    context: TenantContext = Depends(require_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> OnboardingResponse:
    state = await evaluate_onboarding(session, context.tenant_id)
    return OnboardingResponse(
        status=state.status,
        steps=[OnboardingStepResponse(**step.__dict__) for step in state.steps],
    )
