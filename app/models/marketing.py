from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.crm import json_type


class Campaign(TimestampMixin, Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_campaigns_tenant_identity"),
        UniqueConstraint("tenant_id", "external_id", name="uq_campaigns_tenant_external"),
        ForeignKeyConstraint(
            ["tenant_id", "ad_account_channel_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="RESTRICT",
            name="fk_campaigns_tenant_asset",
        ),
        Index("ix_campaigns_tenant_asset", "tenant_id", "ad_account_channel_asset_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    ad_account_channel_asset_id: Mapped[UUID] = mapped_column(nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    objective: Mapped[str] = mapped_column(String(80), nullable=False)
    metrics_snapshot: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(String(500))


class AdSet(TimestampMixin, Base):
    __tablename__ = "ad_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ad_sets_tenant_identity"),
        UniqueConstraint("tenant_id", "campaign_id", "external_id", name="uq_ad_sets_tenant_campaign_external"),
        ForeignKeyConstraint(
            ["tenant_id", "campaign_id"],
            ["campaigns.tenant_id", "campaigns.id"],
            ondelete="CASCADE",
            name="fk_ad_sets_tenant_campaign",
        ),
        Index("ix_ad_sets_tenant_campaign", "tenant_id", "campaign_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    campaign_id: Mapped[UUID] = mapped_column(nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Ad(TimestampMixin, Base):
    __tablename__ = "ads"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ads_tenant_identity"),
        UniqueConstraint("tenant_id", "ad_set_id", "external_id", name="uq_ads_tenant_ad_set_external"),
        ForeignKeyConstraint(
            ["tenant_id", "ad_set_id"],
            ["ad_sets.tenant_id", "ad_sets.id"],
            ondelete="CASCADE",
            name="fk_ads_tenant_ad_set",
        ),
        Index("ix_ads_tenant_ad_set", "tenant_id", "ad_set_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    ad_set_id: Mapped[UUID] = mapped_column(nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
