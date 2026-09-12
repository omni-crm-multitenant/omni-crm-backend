from __future__ import annotations

import asyncio
from uuid import UUID

from app.db.session import SessionFactory
from app.services.contact_privacy import build_contact_export, purge_erased_contacts
from app.services.export_store import put_export
from app.services.jobs import run_job
from app.workers.celery_app import celery_app


@celery_app.task(name="contacts.export")
def export_contact(tenant_id: str, contact_id: str, job_id: str) -> str:
    async def run() -> str:
        async with SessionFactory() as session:
            async with run_job(session, UUID(job_id)) as job:
                document = await build_contact_export(session, UUID(tenant_id), UUID(contact_id))
                reference, expires_at = put_export(document)
                job.result = {"object_ref": reference, "expires_at": expires_at.isoformat()}
            await session.commit()
        return job_id

    return asyncio.run(run())


@celery_app.task(name="contacts.purge_erased")
def purge_erased() -> int:
    async def run() -> int:
        async with SessionFactory() as session:
            purged = await purge_erased_contacts(session)
            await session.commit()
            return purged

    return asyncio.run(run())
