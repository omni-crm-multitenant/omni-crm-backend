from __future__ import annotations

import re
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiProfile


def _tool_decorator(function: Callable) -> Callable:
    """Small compatible tool surface; LangChain remains an optional integration."""
    setattr(function, "name", function.__name__)
    setattr(function, "description", function.__doc__ or "")
    return function


def _entries(source: Any, kind: str) -> list[dict[str, Any]]:
    if isinstance(source, list):
        values = source
    elif isinstance(source, dict):
        values = [{"title": key, "content": value} for key, value in source.items()]
    else:
        values = []
    return [dict(item, kind=kind) if isinstance(item, dict) else {"content": str(item), "kind": kind} for item in values]


def build_catalog_faq_tool(
    session: AsyncSession, *, tenant_id: UUID, profile_id: UUID, profile_version: int,
):
    """Bind a read-only catalog/FAQ tool to one tenant and pinned profile version."""
    @_tool_decorator
    async def query_catalog_faq(query: str) -> dict[str, Any]:
        profile = await session.scalar(select(AiProfile).where(
            AiProfile.tenant_id == tenant_id,
            AiProfile.id == profile_id,
            AiProfile.version == profile_version,
        ))
        if profile is None:
            return {"matches": [], "profile_version": profile_version}
        tokens = set(re.findall(r"[\wáéíóúñü]+", query.casefold()))
        results = []
        for entry in _entries(profile.service_catalog, "catalog") + _entries(profile.faq, "faq"):
            haystack = " ".join(str(value) for key, value in entry.items() if key != "kind").casefold()
            score = sum(token in haystack for token in tokens)
            if score:
                results.append((score, entry))
        results.sort(key=lambda value: (-value[0], str(value[1].get("title", value[1].get("content", "")))))
        return {"matches": [entry for _, entry in results], "profile_version": profile.version}

    return query_catalog_faq
