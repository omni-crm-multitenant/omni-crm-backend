from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.identity import EmailOutbox, EmailVerificationToken, User
from app.core.security import hash_password
from app.services.email import EmailSendResult
from app.services.email_outbox import deliver_email_outbox, mark_stale_email_as_unknown


@pytest.fixture
async def email_database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deliver_email_marks_sent_once(email_database) -> None:
    outbox_id = uuid4()
    async with email_database.begin() as session:
        session.add(
            EmailOutbox(
                id=outbox_id,
                recipient="user@example.com",
                template="generic",
                subject="Verify",
                text_body="Verify account",
                payload={},
            )
        )

    calls = []

    def sender(**message):
        calls.append(message)
        return EmailSendResult(status="sent")

    assert await deliver_email_outbox(email_database, outbox_id, sender=sender) == "sent"
    assert await deliver_email_outbox(email_database, outbox_id, sender=sender) == "sent"
    assert len(calls) == 1
    async with email_database() as session:
        row = await session.scalar(select(EmailOutbox).where(EmailOutbox.id == outbox_id))
        assert row.status == "sent"
        assert row.attempts == 1
        assert row.sent_at is not None


@pytest.mark.asyncio
async def test_stale_processing_becomes_unknown(email_database) -> None:
    outbox_id = uuid4()
    async with email_database.begin() as session:
        session.add(
            EmailOutbox(
                id=outbox_id,
                recipient="user@example.com",
                template="generic",
                subject="Verify",
                text_body="Verify account",
                payload={},
                status="processing",
            )
        )

    assert await mark_stale_email_as_unknown(email_database, outbox_id) is True
    async with email_database() as session:
        row = await session.scalar(select(EmailOutbox).where(EmailOutbox.id == outbox_id))
        assert row.status == "unknown"


@pytest.mark.asyncio
async def test_verification_worker_creates_hash_and_sends_raw_link(email_database) -> None:
    outbox_id = uuid4()
    user_id = uuid4()
    async with email_database.begin() as session:
        session.add(
            User(
                id=user_id,
                name="Verify User",
                email="verify@example.com",
                password_hash=hash_password("strong-password"),
            )
        )
        session.add(
            EmailOutbox(
                id=outbox_id,
                user_id=user_id,
                recipient="verify@example.com",
                template="verify_email",
                subject="Verify",
                text_body="placeholder",
                payload={},
            )
        )

    messages = []

    def sender(**message):
        messages.append(message)
        return EmailSendResult(status="sent")

    assert await deliver_email_outbox(email_database, outbox_id, sender=sender) == "sent"
    assert "/verify-email?token=" in messages[0]["text_body"]
    raw_token = messages[0]["text_body"].split("token=", 1)[1]
    async with email_database() as session:
        token = await session.scalar(select(EmailVerificationToken))
        assert token.token_hash != raw_token
        assert len(token.token_hash) == 64
