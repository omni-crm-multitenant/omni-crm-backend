"""Add review queue for ambiguous contact matches.

Revision ID: 0028_contact_merge_candidates
Revises: 0027_ai_runs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0028_contact_merge_candidates"
down_revision = "0027_ai_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_merge_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id_a", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id_b", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint("status IN ('pending', 'merged', 'dismissed')", name=op.f("ck_contact_merge_candidates_merge_candidate_status")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_contact_merge_candidates_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id_a"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_merge_candidates_contact_a")),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id_b"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_merge_candidates_contact_b")),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_contact_merge_candidates_resolved_by_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_merge_candidates")),
    )
    op.create_index("ix_contact_merge_candidates_tenant_id", "contact_merge_candidates", ["tenant_id"])
    op.create_index("ix_merge_candidates_tenant_status", "contact_merge_candidates", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("contact_merge_candidates")
