"""Add durable conversation handoffs.

Revision ID: 0039_conversation_transfers
Revises: 0038_automation_blocked_status
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0039_conversation_transfers"
down_revision = "0038_automation_blocked_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'expired', 'cancelled')", name="transfer_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "trigger_id", name="uq_transfers_tenant_trigger"),
    )
    op.create_index("ix_conversation_transfers_tenant_id", "conversation_transfers", ["tenant_id"])
    op.create_index("ix_conversation_transfers_conversation_id", "conversation_transfers", ["conversation_id"])
    op.create_index("uq_transfers_pending_conversation", "conversation_transfers", ["tenant_id", "conversation_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index("uq_transfers_pending_conversation", table_name="conversation_transfers")
    op.drop_index("ix_conversation_transfers_conversation_id", table_name="conversation_transfers")
    op.drop_index("ix_conversation_transfers_tenant_id", table_name="conversation_transfers")
    op.drop_table("conversation_transfers")
