"""Add durable restricted webhook inbox.

Revision ID: 0022_webhook_events
Revises: 0021_campaigns
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_webhook_events"
down_revision = "0021_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("routing_external_id", sa.String(255), nullable=False),
        sa.Column("event_kind", sa.String(40), nullable=False),
        sa.Column("native_event_id", sa.String(500), nullable=False),
        sa.Column("event_key", sa.String(700), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("routing_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("channel_asset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), server_default="received", nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_token", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('received', 'quarantined', 'processing', 'processed', 'failed', 'dead_letter')",
            name=op.f("ck_webhook_events_webhook_event_status"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_webhook_events_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_webhook_events_tenant_asset"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "routing_asset_id"],
            ["channel_assets.tenant_id", "channel_assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_webhook_events_routing_asset"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("event_key", name=op.f("uq_webhook_events_event_key")),
    )
    op.create_index("ix_webhook_events_tenant_id", "webhook_events", ["tenant_id"])
    op.create_index("ix_webhook_events_channel_asset_id", "webhook_events", ["channel_asset_id"])
    op.create_index("ix_webhook_events_routing_asset_id", "webhook_events", ["routing_asset_id"])
    op.create_index("ix_webhook_events_pending", "webhook_events", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("webhook_events")
