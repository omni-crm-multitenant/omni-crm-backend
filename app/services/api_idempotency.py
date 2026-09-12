from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_idempotency import ApiIdempotencyKey


class ApiIdempotencyConflict(ValueError):
    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"


def payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


async def reserve_idempotency_key(
    session: AsyncSession, *, scope: str, endpoint: str, key: str, payload: bytes,
    tenant_id: UUID | None = None, ttl_seconds: int = 86400,
) -> ApiIdempotencyKey:
    request_hash = payload_hash(payload)
    existing = await session.scalar(select(ApiIdempotencyKey).where(
        ApiIdempotencyKey.scope == scope, ApiIdempotencyKey.endpoint == endpoint, ApiIdempotencyKey.key == key,
    ).with_for_update())
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApiIdempotencyConflict()
        return existing
    row = ApiIdempotencyKey(
        tenant_id=tenant_id, scope=scope, endpoint=endpoint, key=key,
        request_hash=request_hash, expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(row)
    await session.flush()
    return row
