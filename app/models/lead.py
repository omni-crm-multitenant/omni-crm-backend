from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeadReference(Base):
    __tablename__ = "lead_references"
    __table_args__ = (
        UniqueConstraint("tenant_id", "leadgen_id", name="uq_lead_references_tenant_lead"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_lead_references_tenant_contact"),
        Index("ix_lead_references_tenant_contact", "tenant_id", "contact_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False)
    leadgen_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
