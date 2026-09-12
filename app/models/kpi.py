from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KpiEvent(Base):
    __tablename__ = "kpi_events"
    __table_args__ = (
        CheckConstraint("responder_type IN ('agent', 'ai', 'automation')", name="kpi_responder_type"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            ondelete="CASCADE", name="fk_kpi_events_tenant_conversation",
        ),
        UniqueConstraint("tenant_id", "response_window_id", name="uq_kpi_events_response_window"),
        Index("ix_kpi_events_tenant_received", "tenant_id", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    response_window_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    campaign_id: Mapped[UUID | None] = mapped_column()
    responder_type: Mapped[str] = mapped_column(String(20), nullable=False)
    responder_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    ai_model: Mapped[str | None] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
