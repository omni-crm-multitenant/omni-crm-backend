"""Add tenant-scoped follow-up tasks.

Revision ID: 0029_tasks
Revises: 0028_contact_merge_candidates
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0029_tasks"
down_revision = "0028_contact_merge_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("priority", sa.String(10), server_default="medium", nullable=False),
        sa.Column("status", sa.String(12), server_default="open", nullable=False),
        sa.Column("source", sa.String(12), server_default="user", nullable=False),
        sa.Column("source_ref_id", postgresql.UUID(as_uuid=True)),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True)),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name=op.f("ck_tasks_task_priority")),
        sa.CheckConstraint("status IN ('open', 'done', 'cancelled')", name=op.f("ck_tasks_task_status")),
        sa.CheckConstraint("source IN ('user', 'ai', 'rule', 'system')", name=op.f("ck_tasks_task_source")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_tasks_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_tasks_assigned_user_id_users")),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_tasks_tenant_contact")),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name=op.f("fk_tasks_tenant_conversation")),
        sa.ForeignKeyConstraint(["tenant_id", "opportunity_id"], ["opportunities.tenant_id", "opportunities.id"], ondelete="CASCADE", name=op.f("fk_tasks_tenant_opportunity")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_tenant_id", "tasks", ["tenant_id"])
    op.create_index("ix_tasks_assigned_user_id", "tasks", ["assigned_user_id"])
    op.create_index("ix_tasks_tenant_status_due", "tasks", ["tenant_id", "status", "due_at"])


def downgrade() -> None:
    op.drop_table("tasks")
