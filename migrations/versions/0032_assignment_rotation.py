"""Add round-robin assignment state.

Revision ID: 0032_assignment_rotation
Revises: 0031_attributions
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0032_assignment_rotation"
down_revision = "0031_attributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignment_rotation_state",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_assignment_rotation_state_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["last_assigned_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_assignment_rotation_state_last_assigned_user_id_users")),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_assignment_rotation_state")),
    )


def downgrade() -> None:
    op.drop_table("assignment_rotation_state")
