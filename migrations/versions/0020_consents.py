"""Add tenant-scoped consent event history.

Revision ID: 0020_consents
Revises: 0019_asset_expired_status
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020_consents"
down_revision = "0019_asset_expired_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('granted', 'revoked')", name=op.f("ck_consents_consent_status")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            ondelete="CASCADE",
            name=op.f("fk_consents_tenant_contact"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_consents_tenant_identity")),
    )
    op.create_index("ix_consents_tenant_id", "consents", ["tenant_id"])
    op.create_index("ix_consents_contact_id", "consents", ["contact_id"])
    op.create_index(
        "ix_consents_tenant_contact_purpose",
        "consents",
        ["tenant_id", "contact_id", "channel", "purpose"],
    )


def downgrade() -> None:
    op.drop_table("consents")
