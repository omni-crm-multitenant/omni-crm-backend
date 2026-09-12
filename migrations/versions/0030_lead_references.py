"""Add hashed lead references linked to contacts.

Revision ID: 0030_lead_references
Revises: 0029_tasks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030_lead_references"
down_revision = "0029_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leadgen_id", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_lead_references_tenant_contact")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_references")),
        sa.UniqueConstraint("tenant_id", "leadgen_id", name=op.f("uq_lead_references_tenant_lead")),
    )
    op.create_index("ix_lead_references_tenant_id", "lead_references", ["tenant_id"])
    op.create_index("ix_lead_references_tenant_contact", "lead_references", ["tenant_id", "contact_id"])


def downgrade() -> None:
    op.drop_table("lead_references")
