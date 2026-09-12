from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.sanitization import REDACTED, sanitize_metadata
from app.db.base import Base
from app.models.identity import Tenant, User
from app.models.operations import AuditEvent, ImmutableAuditEventError, IngressDiagnostic
from app.services.audit import write_audit_event


def test_recursive_sanitizer_redacts_sensitive_keys_and_pii_patterns() -> None:
    sanitized = sanitize_metadata(
        {
            "password": "visible",
            "nested": [
                {"Authorization": "Bearer abc"},
                "ana@example.com",
                {"note": "call +57 300 123 4567", "id": "safe-id"},
                "sk-abcdefghijklmnopqrstuvwxyz",
            ],
        }
    )
    assert sanitized["password"] == REDACTED
    assert sanitized["nested"][0]["Authorization"] == REDACTED
    assert sanitized["nested"][1] == REDACTED
    assert sanitized["nested"][2] == {"note": f"call {REDACTED}", "id": "safe-id"}
    assert sanitized["nested"][3] == REDACTED


@pytest.mark.asyncio
async def test_audit_writer_is_sanitized_transactional_and_immutable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id, user_id = uuid4(), uuid4()
    async with factory.begin() as session:
        session.add_all(
            [
                Tenant(id=tenant_id, name="Audit Tenant", slug=f"audit-{tenant_id.hex[:8]}"),
                User(id=user_id, name="Auditor", email=f"{user_id.hex}@example.test", password_hash="x"),
            ]
        )
    async with factory.begin() as session:
        event = await write_audit_event(
            session,
            tenant_id=tenant_id,
            actor_type="user",
            actor_user_id=user_id,
            action="resource.created",
            resource_type="resource",
            resource_id=uuid4(),
            metadata={"token": "secret", "customer": "ana@example.com", "safe": "ok"},
        )
        event_id = event.id
    async with factory() as session:
        persisted = await session.get(AuditEvent, event_id)
        assert persisted.sanitized_metadata == {"token": REDACTED, "customer": REDACTED, "safe": "ok"}

    async with factory() as session:
        await write_audit_event(
            session,
            tenant_id=tenant_id,
            actor_type="system",
            action="rolled.back",
            resource_type="test",
        )
        await session.rollback()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 1

    async with factory() as session:
        persisted = await session.get(AuditEvent, event_id)
        persisted.action = "tampered"
        with pytest.raises(ImmutableAuditEventError):
            await session.flush()
        await session.rollback()
    async with factory() as session:
        persisted = await session.get(AuditEvent, event_id)
        await session.delete(persisted)
        with pytest.raises(ImmutableAuditEventError):
            await session.flush()
        await session.rollback()
    await engine.dispose()


def test_ingress_diagnostics_are_not_tenant_audit_rows() -> None:
    assert "tenant_id" not in IngressDiagnostic.__table__.columns
    assert "tenant_id" in AuditEvent.__table__.columns
