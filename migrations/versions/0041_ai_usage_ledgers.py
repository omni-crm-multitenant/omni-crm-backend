"""Add monthly AI token ledgers.

Revision ID: 0041_ai_usage_ledgers
Revises: 0040_ai_limits
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0041_ai_usage_ledgers"
down_revision = "0040_ai_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_ledgers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "month", name="uq_ai_usage_tenant_month"),
    )
    op.create_index("ix_ai_usage_ledgers_tenant_id", "ai_usage_ledgers", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_ledgers_tenant_id", table_name="ai_usage_ledgers")
    op.drop_table("ai_usage_ledgers")
