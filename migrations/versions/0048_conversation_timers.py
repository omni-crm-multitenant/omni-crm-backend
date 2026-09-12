"""Add durable conversation timers.

Revision ID: 0048_conversation_timers
Revises: 0047_contact_erasure
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0048_conversation_timers"
down_revision = "0047_contact_erasure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_timers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(40), nullable=False),
        sa.Column("activity_version", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("trigger_message_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'fired', 'cancelled')", name="conversation_timer_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name="fk_conversation_timers_tenant_conversation"),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", "rule_id", "rule_version", "activity_version", name="uq_conversation_timer_activity"),
    )
    op.create_index("ix_conversation_timers_tenant_id", "conversation_timers", ["tenant_id"])
    op.create_index("ix_conversation_timers_due", "conversation_timers", ["status", "deadline"])


def downgrade() -> None:
    op.drop_index("ix_conversation_timers_due", table_name="conversation_timers")
    op.drop_index("ix_conversation_timers_tenant_id", table_name="conversation_timers")
    op.drop_table("conversation_timers")
