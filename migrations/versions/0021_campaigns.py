"""Add read-only campaign snapshots.

Revision ID: 0021_campaigns
Revises: 0020_consents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0021_campaigns"
down_revision = "0020_consents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ad_account_channel_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("objective", sa.String(80), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ad_account_channel_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_campaigns_tenant_asset"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_campaigns_tenant_identity")),
        sa.UniqueConstraint("tenant_id", "external_id", name=op.f("uq_campaigns_tenant_external")),
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])
    op.create_index("ix_campaigns_tenant_asset", "campaigns", ["tenant_id", "ad_account_channel_asset_id"])


def downgrade() -> None:
    op.drop_table("campaigns")
