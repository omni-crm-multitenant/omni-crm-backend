from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint, event, func, text, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


json_type = JSON().with_variant(postgresql.JSONB(), "postgresql")


class ImmutableAuditEventError(RuntimeError):
    pass


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'ai', 'system', 'integration')",
            name="audit_actor_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sanitized_metadata: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)


class IngressDiagnostic(Base):
    __tablename__ = "ingress_diagnostics"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    routing_key_hash: Mapped[str | None] = mapped_column(String(64))
    sanitized_metadata: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_webhook_events_event_key"),
        CheckConstraint(
            "status IN ('received', 'quarantined', 'processing', 'processed', 'failed', 'dead_letter')",
            name="webhook_event_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="RESTRICT",
            name="fk_webhook_events_tenant_asset",
        ),
        Index("ix_webhook_events_pending", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    routing_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    native_event_id: Mapped[str] = mapped_column(String(500), nullable=False)
    event_key: Mapped[str] = mapped_column(String(700), nullable=False)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    routing_asset_id: Mapped[UUID | None] = mapped_column(index=True)
    channel_asset_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received", server_default="received")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    error_code: Mapped[str | None] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    business_hours: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    off_hours_policy: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    contact_info: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    automations_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=512, server_default="512")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=8, server_default="8")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    monthly_token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=100000, server_default="100000")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


def _reject_audit_mutation(_mapper, _connection, _target) -> None:
    raise ImmutableAuditEventError("AUDIT_EVENTS_ARE_APPEND_ONLY")


event.listen(AuditEvent, "before_update", _reject_audit_mutation)
event.listen(AuditEvent, "before_delete", _reject_audit_mutation)
