from celery import Celery  # type: ignore[import-untyped]

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "omni",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.email_tasks", "app.workers.webhook_tasks", "app.workers.campaign_tasks", "app.workers.outbox_tasks", "app.workers.contact_privacy_tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "campaign-reconciliation": {
            "task": "campaigns.reconcile",
            "schedule": settings.campaign_sync_interval_seconds,
        },
        "outbox-relay": {
            "task": "outbox.relay",
            "schedule": 5,
        },
        "purge-erased-contacts": {
            "task": "contacts.purge_erased",
            "schedule": 3600,
        },
    },
)
