from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContactMergeCandidate(Base):
    __tablename__ = "contact_merge_candidates"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'merged', 'dismissed')", name="merge_candidate_status"),
        ForeignKeyConstraint(["tenant_id", "contact_id_a"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_merge_candidates_contact_a"),
        ForeignKeyConstraint(["tenant_id", "contact_id_b"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_merge_candidates_contact_b"),
        Index("ix_merge_candidates_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id_a: Mapped[UUID] = mapped_column(nullable=False)
    contact_id_b: Mapped[UUID] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
