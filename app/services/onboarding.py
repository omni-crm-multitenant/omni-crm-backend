from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiProfile
from app.models.identity import ChannelAsset, Membership, Tenant, User
from app.models.operations import TenantSettings


OnboardingStatus = Literal["not_started", "in_progress", "action_required", "completed", "failed"]


@dataclass(frozen=True)
class OnboardingStep:
    key: str
    status: OnboardingStatus = "not_started"
    reason_code: str | None = None
    blocking: bool = True

    @property
    def satisfied(self) -> bool:
        return self.status == "completed"


REQUIRED_ONBOARDING_STEPS = (
    "registration", "email_verification", "mfa", "meta_asset",
    "tenant_settings", "ai_profile", "team_invites",
)


def initial_onboarding_steps() -> list[OnboardingStep]:
    return [OnboardingStep(key=key) for key in REQUIRED_ONBOARDING_STEPS]


async def evaluate_registration(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    found = await session.scalar(select(exists().where(Membership.tenant_id == tenant_id)))
    return OnboardingStep("registration", "completed" if found else "not_started")


async def evaluate_email_verification(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    verified = await session.scalar(select(exists().where(
        Membership.tenant_id == tenant_id,
        Membership.user_id == User.id,
        User.email_verified_at.is_not(None),
        User.status == "active",
    )))
    if verified:
        return OnboardingStep("email_verification", "completed")
    return OnboardingStep("email_verification", "action_required", "EMAIL_VERIFICATION_REQUIRED")


async def evaluate_mfa(session: AsyncSession, tenant_id: UUID, *, required: bool = False) -> OnboardingStep:
    if not required:
        return OnboardingStep("mfa", "completed", "MFA_NOT_REQUIRED", blocking=False)
    configured = await session.scalar(select(exists().where(
        Membership.tenant_id == tenant_id,
        Membership.user_id == User.id,
        User.mfa_enabled.is_(True),
        User.status == "active",
    )))
    if configured:
        return OnboardingStep("mfa", "completed")
    return OnboardingStep("mfa", "action_required", "MFA_REQUIRED")


async def evaluate_meta_asset(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    connected = await session.scalar(select(exists().where(
        ChannelAsset.tenant_id == tenant_id,
        ChannelAsset.status == "connected",
        ChannelAsset.channel.in_(("whatsapp", "messenger", "instagram")),
    )))
    if connected:
        return OnboardingStep("meta_asset", "completed")
    if await session.scalar(select(exists().where(ChannelAsset.tenant_id == tenant_id, ChannelAsset.status == "error"))):
        return OnboardingStep("meta_asset", "failed", "META_CONNECTION_FAILED")
    if await session.scalar(select(exists().where(ChannelAsset.tenant_id == tenant_id, ChannelAsset.status == "expired"))):
        return OnboardingStep("meta_asset", "action_required", "META_TOKEN_EXPIRED")
    return OnboardingStep("meta_asset", "action_required", "META_ASSET_REQUIRED")


async def evaluate_tenant_settings(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    settings = await session.get(TenantSettings, tenant_id)
    configured = bool(settings and any(settings.business_hours.get(day) for day in (
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    )))
    if configured:
        return OnboardingStep("tenant_settings", "completed")
    return OnboardingStep("tenant_settings", "action_required", "BUSINESS_HOURS_REQUIRED")


async def evaluate_ai_profile(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    configured = await session.scalar(select(exists().where(
        AiProfile.tenant_id == tenant_id,
        AiProfile.active.is_(True),
    )))
    if configured:
        return OnboardingStep("ai_profile", "completed")
    return OnboardingStep("ai_profile", "action_required", "AI_PROFILE_REQUIRED")


async def evaluate_team_invites(session: AsyncSession, tenant_id: UUID) -> OnboardingStep:
    extra_member = await session.scalar(select(exists().where(
        Membership.tenant_id == tenant_id,
        Membership.role != "administrador",
        Membership.status == "active",
    )))
    return OnboardingStep(
        "team_invites", "completed", "TEAM_MEMBER_ADDED" if extra_member else "TEAM_INVITES_OPTIONAL", blocking=False,
    )


def derive_onboarding_status(steps: list[OnboardingStep]) -> OnboardingStatus:
    if not any(step.satisfied for step in steps):
        return "not_started"
    required = [step for step in steps if step.blocking]
    if any(step.status == "failed" for step in required):
        return "failed"
    if any(step.status == "action_required" for step in required):
        return "action_required"
    if required and all(step.satisfied for step in required):
        return "completed"
    return "in_progress"


@dataclass(frozen=True)
class OnboardingState:
    status: OnboardingStatus
    steps: tuple[OnboardingStep, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "steps": [asdict(step) for step in self.steps]}


async def evaluate_onboarding(session: AsyncSession, tenant_id: UUID) -> OnboardingState:
    if await session.get(Tenant, tenant_id) is None:
        return OnboardingState("not_started", tuple(initial_onboarding_steps()))
    steps = [
        await evaluate_registration(session, tenant_id),
        await evaluate_email_verification(session, tenant_id),
        await evaluate_mfa(session, tenant_id),
        await evaluate_meta_asset(session, tenant_id),
        await evaluate_tenant_settings(session, tenant_id),
        await evaluate_ai_profile(session, tenant_id),
        await evaluate_team_invites(session, tenant_id),
    ]
    return OnboardingState(derive_onboarding_status(steps), tuple(steps))
