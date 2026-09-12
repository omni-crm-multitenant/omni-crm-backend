"""Add tenant-scoped conversation graph checkpoints.

Revision ID: 0035_graph_checkpoints
Revises: 0034_automation_executions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0035_graph_checkpoints"
down_revision = "0034_automation_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graph_checkpoints",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name=op.f("fk_graph_checkpoints_tenant_conversation")),
        sa.PrimaryKeyConstraint("tenant_id", "conversation_id", name=op.f("pk_graph_checkpoints")),
    )


def downgrade() -> None:
    op.drop_table("graph_checkpoints")
