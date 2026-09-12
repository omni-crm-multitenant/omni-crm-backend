"""Add replay-safe billing usage events.

Revision ID: 0050_billing_usage_events
Revises: 0049_billing_schema
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0050_billing_usage_events"
down_revision = "0049_billing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("meter", sa.String(40), nullable=False), sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "subscription_id", "meter", "event_key", name="uq_billing_usage_event"),
    )
    op.create_index("ix_billing_usage_events_tenant_id", "billing_usage_events", ["tenant_id"])
    op.create_index("ix_billing_usage_period", "billing_usage_events", ["tenant_id", "subscription_id", "meter"])


def downgrade() -> None:
    op.drop_index("ix_billing_usage_period", table_name="billing_usage_events")
    op.drop_index("ix_billing_usage_events_tenant_id", table_name="billing_usage_events")
    op.drop_table("billing_usage_events")
