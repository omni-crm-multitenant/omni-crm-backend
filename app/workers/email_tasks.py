import asyncio
from uuid import UUID

from app.db.session import SessionFactory
from app.services.email_outbox import deliver_email_outbox
from app.workers.celery_app import celery_app


@celery_app.task(name="email.deliver", bind=True, max_retries=5)
def deliver_email(self, outbox_id: str) -> str:
    try:
        return asyncio.run(deliver_email_outbox(SessionFactory, UUID(outbox_id)))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(300, 5 * (2**self.request.retries)))

