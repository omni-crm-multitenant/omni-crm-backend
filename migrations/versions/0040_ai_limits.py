"""Add tenant AI execution limits.

Revision ID: 0040_ai_limits
Revises: 0039_conversation_transfers
"""

from alembic import op
import sqlalchemy as sa


revision = "0040_ai_limits"
down_revision = "0039_conversation_transfers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, default in (("max_output_tokens", 512), ("timeout_seconds", 30), ("max_tool_calls", 8), ("max_retries", 2), ("monthly_token_budget", 100000)):
        op.add_column("tenant_settings", sa.Column(name, sa.Integer(), server_default=str(default), nullable=False))


def downgrade() -> None:
    for name in ("monthly_token_budget", "max_retries", "max_tool_calls", "timeout_seconds", "max_output_tokens"):
        op.drop_column("tenant_settings", name)
