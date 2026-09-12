from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageSendAttempt(Base):
    """Durable provider-attempt evidence; unknown is never an auto-retry signal."""

    __tablename__ = "message_send_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('dispatching', 'accepted', 'rejected', 'unknown')",
            name="message_send_attempt_status",
        ),
        Index("ix_message_send_attempts_message", "tenant_id", "message_id", "attempt_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
