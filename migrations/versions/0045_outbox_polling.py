"""Add outbox polling index and retry schedule.

Revision ID: 0045_outbox_polling
Revises: 0044_jobs
"""

from alembic import op
import sqlalchemy as sa


revision = "0045_outbox_polling"
down_revision = "0044_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_outbox_events_unpublished", "outbox_events", ["published_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.drop_column("outbox_events", "next_attempt_at")
