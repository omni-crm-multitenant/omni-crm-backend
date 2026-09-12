from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationTimer(Base):
    __tablename__ = "conversation_timers"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'fired', 'cancelled')", name="conversation_timer_status"),
        UniqueConstraint("tenant_id", "conversation_id", "rule_id", "rule_version", "activity_version", name="uq_conversation_timer_activity"),
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name="fk_conversation_timers_tenant_conversation"),
        Index("ix_conversation_timers_due", "status", "deadline"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)
    activity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", server_default="pending")
    trigger_message_id: Mapped[UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
