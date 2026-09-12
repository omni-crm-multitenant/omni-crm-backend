from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="task_priority"),
        CheckConstraint("status IN ('open', 'done', 'cancelled')", name="task_status"),
        CheckConstraint("source IN ('user', 'ai', 'rule', 'system')", name="task_source"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_tasks_tenant_contact"),
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name="fk_tasks_tenant_conversation"),
        ForeignKeyConstraint(["tenant_id", "opportunity_id"], ["opportunities.tenant_id", "opportunities.id"], ondelete="CASCADE", name="fk_tasks_tenant_opportunity"),
        Index("ix_tasks_tenant_status_due", "tenant_id", "status", "due_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    assigned_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium", server_default="medium")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open", server_default="open")
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="user", server_default="user")
    source_ref_id: Mapped[UUID | None] = mapped_column()
    contact_id: Mapped[UUID | None] = mapped_column()
    conversation_id: Mapped[UUID | None] = mapped_column()
    opportunity_id: Mapped[UUID | None] = mapped_column()
