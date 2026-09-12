from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionFactory
from app.models.operations import WebhookEvent
from app.workers.celery_app import celery_app
from app.core.request_context import request_id_var


async def enqueue_pending_webhooks(limit: int = 100) -> int:
    async with SessionFactory() as session:
        result = await session.scalars(
            select(WebhookEvent.id)
            .where(WebhookEvent.status == "received", WebhookEvent.next_attempt_at <= datetime.now(UTC))
            .order_by(WebhookEvent.received_at.asc(), WebhookEvent.id.asc())
            .limit(limit)
        )
        ids = list(result.all())
    for event_id in ids:
        process_webhook.delay(str(event_id))
    return len(ids)


@celery_app.task(name="webhook.process", bind=True, max_retries=5)
def process_webhook(self, event_id: str, request_id: str | None = None) -> str:
    """Relay target; durable inbox row remains the source of truth for processing."""
    if request_id:
        request_id_var.set(request_id)
    return event_id


@celery_app.task(name="webhook.relay")
def relay_pending_webhooks() -> int:
    return asyncio.run(enqueue_pending_webhooks())
