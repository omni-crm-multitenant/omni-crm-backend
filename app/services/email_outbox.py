import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.identity import EmailOutbox
from app.services.email import EmailSendResult, send_email
from app.services.email_verification import issue_verification_token


EmailSender = Callable[..., EmailSendResult]


async def deliver_email_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    outbox_id: UUID,
    *,
    sender: EmailSender = send_email,
) -> str:
    async with session_factory.begin() as session:
        row = await session.scalar(
            select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update()
        )
        if row is None:
            return "missing"
        if row.status in {"sent", "processing", "unknown"}:
            return row.status
        row.status = "processing"
        row.processing_started_at = datetime.now(UTC)
        row.attempts += 1
        if row.template == "verify_email":
            if row.user_id is None:
                row.status = "failed"
                row.last_error = "VERIFICATION_USER_MISSING"
                row.processing_started_at = None
                return row.status
            raw_token = await issue_verification_token(session, row.user_id)
            base_url = str(get_settings().auth_public_base_url).rstrip("/")
            verification_url = f"{base_url}/verify-email?token={raw_token}"
            message: dict[str, str | None] = {
                "recipient": row.recipient,
                "subject": row.subject,
                "text_body": f"Verifica tu cuenta: {verification_url}",
                "html_body": f'<p>Verifica tu cuenta:</p><p><a href="{verification_url}">Verificar cuenta</a></p>',
            }
        else:
            message = {
                "recipient": row.recipient,
                "subject": row.subject,
                "text_body": row.text_body,
                "html_body": row.html_body,
            }

    result = await asyncio.to_thread(sender, **message)

    async with session_factory.begin() as session:
        row = await session.scalar(
            select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update()
        )
        if row is None:
            return "missing"
        row.status = result.status
        row.last_error = result.error
        row.processing_started_at = None
        if result.status == "sent":
            row.sent_at = datetime.now(UTC)
        return row.status


async def mark_stale_email_as_unknown(
    session_factory: async_sessionmaker[AsyncSession],
    outbox_id: UUID,
) -> bool:
    async with session_factory.begin() as session:
        row = await session.scalar(
            select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update()
        )
        if row is None or row.status != "processing":
            return False
        row.status = "unknown"
        row.last_error = "WORKER_RESULT_UNKNOWN"
        row.processing_started_at = None
        return True
