from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


AUTOMATION_TRIGGERS = "'lead_created', 'message_received', 'stage_changed', 'customer_unanswered', 'team_unanswered', 'task_created', 'opportunity_won', 'opportunity_lost'"


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    __table_args__ = (
        CheckConstraint(f"trigger_type IN ({AUTOMATION_TRIGGERS})", name="automation_rule_trigger_type"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds > 0", name="automation_rule_duration"),
        CheckConstraint("clock IS NULL OR clock IN ('elapsed', 'business')", name="automation_rule_clock"),
        Index("ix_automation_rules_tenant_enabled", "tenant_id", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    clock: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
