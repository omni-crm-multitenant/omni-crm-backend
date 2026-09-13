import os
import time
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.services.email import send_email
from app.services.rate_limiter import RedisSlidingWindowLimiter


DATABASE_URL = os.getenv("TEST_DATABASE_URL")
REDIS_URL = os.getenv("TEST_REDIS_URL")
MAILPIT_URL = os.getenv("TEST_MAILPIT_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is required")
@pytest.mark.asyncio
async def test_postgres_schema_exists_after_migrations() -> None:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(text("SELECT to_regclass('public.tenants')"))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert result == "tenants"
        assert revision
    finally:
        await engine.dispose()


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is required")
@pytest.mark.asyncio
async def test_redis_limiter_is_atomic_and_shared() -> None:
    assert REDIS_URL is not None
    redis = redis_from_url(REDIS_URL)
    key = f"integration:rate-limit:{uuid4()}"
    try:
        limiter = RedisSlidingWindowLimiter(redis)
        outcomes = [await limiter.check_limit(key, limit=2, window_seconds=30) for _ in range(3)]
        assert [item.allowed for item in outcomes] == [True, True, False]
        assert outcomes[-1].retry_after >= 1
    finally:
        await redis.delete(key)
        await redis.aclose()


@pytest.mark.skipif(not (MAILPIT_URL and os.getenv("SMTP_HOST")), reason="Mailpit integration variables are required")
def test_mailpit_receives_smtp_message() -> None:
    assert MAILPIT_URL is not None
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "1025"))
    subject = f"integration-{uuid4()}"
    result = send_email(
        "integration@example.test",
        subject,
        "Mailpit integration message",
        settings=Settings(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            mail_from="integration@omni.test",
        ),
    )
    assert result.status == "sent"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = httpx.get(f"{MAILPIT_URL}/api/v1/messages", timeout=2)
        response.raise_for_status()
        messages = response.json().get("messages", [])
        if any(item.get("Subject") == subject for item in messages):
            return
        time.sleep(0.25)
    pytest.fail(f"Mailpit did not receive message {subject}")
