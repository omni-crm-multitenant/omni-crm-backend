from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiProfile


async def save_ai_profile(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    created_by_user_id: UUID,
    instructions: str,
    service_catalog: dict[str, Any] | None = None,
    faq: dict[str, Any] | None = None,
    tone: str = "professional",
    language: str = "es",
    provider: str = "openai",
    model: str = "default",
) -> AiProfile:
    profiles = list((await session.scalars(select(AiProfile).where(AiProfile.tenant_id == tenant_id).with_for_update())).all())
    for profile in profiles:
        profile.active = False
    max_version = max((profile.version for profile in profiles), default=0)
    profile = AiProfile(
        tenant_id=tenant_id, version=max_version + 1, instructions=instructions,
        service_catalog=service_catalog or {}, faq=faq or {}, tone=tone, language=language,
        provider=provider, model=model, active=True, created_by_user_id=created_by_user_id,
    )
    session.add(profile)
    await session.flush()
    return profile
