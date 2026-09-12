"""Add contact attribution records.

Revision ID: 0031_attributions
Revises: 0030_lead_references
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0031_attributions"
down_revision = "0030_lead_references"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ad_set_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ad_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("raw_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence IN ('complete', 'partial', 'unknown')", name=op.f("ck_attributions_attribution_confidence")),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_attributions_tenant_contact")),
        sa.ForeignKeyConstraint(["tenant_id", "campaign_id"], ["campaigns.tenant_id", "campaigns.id"], ondelete="RESTRICT", name=op.f("fk_attributions_tenant_campaign")),
        sa.ForeignKeyConstraint(["tenant_id", "ad_set_id"], ["ad_sets.tenant_id", "ad_sets.id"], ondelete="RESTRICT", name=op.f("fk_attributions_tenant_ad_set")),
        sa.ForeignKeyConstraint(["tenant_id", "ad_id"], ["ads.tenant_id", "ads.id"], ondelete="RESTRICT", name=op.f("fk_attributions_tenant_ad")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attributions")),
    )
    op.create_index("ix_attributions_tenant_id", "attributions", ["tenant_id"])
    op.create_index("ix_attributions_tenant_contact", "attributions", ["tenant_id", "contact_id"])


def downgrade() -> None:
    op.drop_table("attributions")
