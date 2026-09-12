from __future__ import annotations

import asyncio

from app.db.session import SessionFactory
from app.services.outbox_relay import relay_outbox_events
from app.workers.celery_app import celery_app


@celery_app.task(name="outbox.relay")
def relay_pending_outbox() -> int:
    async def run() -> int:
        async with SessionFactory() as session:
            published = await relay_outbox_events(session)
            await session.commit()
            return published

    return asyncio.run(run())
