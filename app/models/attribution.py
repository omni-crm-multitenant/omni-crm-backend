from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attribution(Base):
    __tablename__ = "attributions"
    __table_args__ = (
        CheckConstraint("confidence IN ('complete', 'partial', 'unknown')", name="attribution_confidence"),
        ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name="fk_attributions_tenant_contact"),
        ForeignKeyConstraint(["tenant_id", "campaign_id"], ["campaigns.tenant_id", "campaigns.id"], ondelete="SET NULL", name="fk_attributions_tenant_campaign"),
        ForeignKeyConstraint(["tenant_id", "ad_set_id"], ["ad_sets.tenant_id", "ad_sets.id"], ondelete="SET NULL", name="fk_attributions_tenant_ad_set"),
        ForeignKeyConstraint(["tenant_id", "ad_id"], ["ads.tenant_id", "ads.id"], ondelete="SET NULL", name="fk_attributions_tenant_ad"),
        Index("ix_attributions_tenant_contact", "tenant_id", "contact_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(nullable=False)
    campaign_id: Mapped[UUID | None] = mapped_column()
    ad_set_id: Mapped[UUID | None] = mapped_column()
    ad_id: Mapped[UUID | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
