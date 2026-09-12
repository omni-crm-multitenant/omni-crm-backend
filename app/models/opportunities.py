from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.crm import json_type


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_opportunities_tenant_identity"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_opportunities_tenant_contact"),
        ForeignKeyConstraint(["tenant_id", "pipeline_id"], ["pipelines.tenant_id", "pipelines.id"], ondelete="RESTRICT", name="fk_opportunities_tenant_pipeline"),
        ForeignKeyConstraint(["tenant_id", "stage_id"], ["pipeline_stages.tenant_id", "pipeline_stages.id"], ondelete="RESTRICT", name="fk_opportunities_tenant_stage"),
        Index("ix_opportunities_tenant_contact", "tenant_id", "contact_id"),
        Index("ix_opportunities_tenant_pipeline", "tenant_id", "pipeline_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False)
    pipeline_id: Mapped[UUID] = mapped_column(nullable=False)
    stage_id: Mapped[UUID] = mapped_column(nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    loss_reason: Mapped[str | None] = mapped_column(String(255))
    expected_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    custom_fields: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
