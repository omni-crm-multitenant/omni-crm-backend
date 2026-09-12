"""Add server-owned billing schema.

Revision ID: 0049_billing_schema
Revises: 0048_conversation_timers
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0049_billing_schema"
down_revision = "0048_conversation_timers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False), sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("interval", sa.String(12), server_default="month", nullable=False), sa.Column("contact_limit", sa.Integer(), nullable=False),
        sa.Column("conversation_limit", sa.Integer(), nullable=False), sa.Column("asset_limit", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name="billing_plan_currency"), sa.CheckConstraint("amount_minor >= 0", name="billing_plan_amount"),
        sa.CheckConstraint("interval = 'month'", name="billing_plan_interval"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "version", name="uq_billing_plan_code_version"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("payment_period_start", sa.Date(), nullable=False),
        sa.Column("payment_period_end", sa.Date(), nullable=False), sa.Column("paid_through", sa.Date()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled')", name="subscription_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", name="uq_subscriptions_tenant"),
    )
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("provider_reference", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False), sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="payment_amount"), sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="RESTRICT"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payments_provider_reference"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])
    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)), sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_event_id", sa.String(255), nullable=False), sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_billing_events_provider_event"),
    )
    op.create_index("ix_billing_events_tenant_id", "billing_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_events_tenant_id", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_index("ix_payments_tenant_id", table_name="payments")
    op.drop_table("payments")
    op.drop_table("subscriptions")
    op.drop_table("billing_plans")
