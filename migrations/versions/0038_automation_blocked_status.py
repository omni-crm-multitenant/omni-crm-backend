"""Allow automation executions to record policy blocks.

Revision ID: 0038_automation_blocked_status
Revises: 0037_message_idempotency_attempts
"""

from alembic import op


revision = "0038_automation_blocked_status"
down_revision = "0037_message_idempotency_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("automation_execution_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "automation_execution_status",
        "automation_executions",
        "status IN ('received', 'processing', 'success', 'partial', 'failed', 'dead_letter', 'skipped_depth_limit', 'blocked')",
    )


def downgrade() -> None:
    op.drop_constraint("automation_execution_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "automation_execution_status",
        "automation_executions",
        "status IN ('received', 'processing', 'success', 'partial', 'failed', 'dead_letter', 'skipped_depth_limit')",
    )
