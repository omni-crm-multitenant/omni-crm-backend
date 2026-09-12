"""Add AI stage transition policy.

Revision ID: 0036_pipeline_ai_transition
Revises: 0035_graph_checkpoints
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_pipeline_ai_transition"
down_revision = "0035_graph_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_stages", sa.Column("ai_can_transition", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("pipeline_stages", "ai_can_transition")
