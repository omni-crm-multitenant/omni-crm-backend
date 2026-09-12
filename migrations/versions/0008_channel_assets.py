"""Add tenant-owned channel assets.

Revision ID: 0008_channel_assets
Revises: 0007_password_reset
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_channel_assets"
down_revision = "0007_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("meta_app_id", sa.String(255), nullable=False),
        sa.Column("credential_ref", sa.String(255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="connected", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("channel IN ('whatsapp', 'messenger', 'instagram', 'ad_account')", name=op.f("ck_channel_assets_channel_asset_channel")),
        sa.CheckConstraint("status IN ('connected', 'disconnected', 'error')", name=op.f("ck_channel_assets_channel_asset_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_channel_assets_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_assets")),
    )
    op.create_index("ix_channel_assets_tenant_id", "channel_assets", ["tenant_id"])
    op.create_index(
        "uq_connected_messaging_asset_owner",
        "channel_assets",
        ["meta_app_id", "channel", "external_id"],
        unique=True,
        postgresql_where=sa.text("status = 'connected' AND channel IN ('whatsapp', 'messenger', 'instagram')"),
    )


def downgrade() -> None:
    op.drop_table("channel_assets")
