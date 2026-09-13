from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.crm import json_type


class AiProfile(Base):
    __tablename__ = "ai_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_profiles_tenant_identity"),
        UniqueConstraint("tenant_id", "version", name="uq_ai_profiles_tenant_version"),
        Index("uq_ai_profiles_active_tenant", "tenant_id", unique=True, postgresql_where=text("active = true"), sqlite_where=text("active = 1")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    service_catalog: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    faq: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    tone: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AiRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "conversation_id", "trigger_message_id", name="uq_ai_runs_trigger"),
        CheckConstraint("status IN ('pending', 'running', 'success', 'error', 'transferred', 'cancelled')", name="ai_run_status"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"],
            ondelete="CASCADE", name="fk_ai_runs_tenant_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "profile_id"], ["ai_profiles.tenant_id", "ai_profiles.id"],
            ondelete="RESTRICT", name="fk_ai_runs_tenant_profile",
        ),
        Index("ix_ai_runs_tenant_conversation", "tenant_id", "conversation_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    profile_id: Mapped[UUID] = mapped_column(nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_message_id: Mapped[UUID] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    latency_ms: Mapped[int | None] = mapped_column(BigInteger)
    token_usage: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    control_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
