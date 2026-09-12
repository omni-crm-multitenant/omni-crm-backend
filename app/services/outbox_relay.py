from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent


EnqueueEvent = Callable[[dict[str, Any]], Any | Awaitable[Any]]


async def _default_enqueue(payload: dict[str, Any]) -> Any:
    from app.workers.celery_app import celery_app
    return celery_app.send_task("automation.process_event", args=[payload])


async def relay_outbox_events(
    session: AsyncSession,
    *,
    enqueue: EnqueueEvent | None = None,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    enqueue = enqueue or _default_enqueue
    rows = list((await session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None), OutboxEvent.next_attempt_at <= now)
        .order_by(OutboxEvent.created_at.asc(), OutboxEvent.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )).all())
    published = 0
    for row in rows:
        row.attempts += 1
        try:
            result = enqueue(dict(row.payload or {}))
            if inspect.isawaitable(result):
                await result
        except Exception:
            row.next_attempt_at = now + timedelta(seconds=min(300, 2 ** min(row.attempts, 8)))
            continue
        row.published_at = now
        row.next_attempt_at = now
        published += 1
    await session.flush()
    return published
