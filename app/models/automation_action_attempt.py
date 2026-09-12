from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationActionAttempt(Base):
    __tablename__ = "automation_action_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "execution_id", "action_index", name="uq_automation_action_execution_index"),
        CheckConstraint("status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown', 'cancelled')", name="automation_action_attempt_status"),
        Index("ix_automation_action_attempts_pending", "tenant_id", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False)
    action_index: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    send_intent_id: Mapped[UUID | None] = mapped_column()
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
