"""Add campaign ad set and ad reference tables.

Revision ID: 0023_ad_sets_ads
Revises: 0022_webhook_events
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023_ad_sets_ads"
down_revision = "0022_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, parent_table, parent_column, unique_name, fk_name, index_name in (
        ("ad_sets", "campaigns", "campaign_id", "uq_ad_sets_tenant_identity", "fk_ad_sets_tenant_campaign", "ix_ad_sets_tenant_campaign"),
        ("ads", "ad_sets", "ad_set_id", "uq_ads_tenant_identity", "fk_ads_tenant_ad_set", "ix_ads_tenant_ad_set"),
    ):
        external_unique = "uq_ad_sets_tenant_campaign_external" if table == "ad_sets" else "uq_ads_tenant_ad_set_external"
        parent_fk = ["campaigns.tenant_id", "campaigns.id"] if table == "ad_sets" else ["ad_sets.tenant_id", "ad_sets.id"]
        op.create_table(
            table,
            sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(parent_column, postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("external_id", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(
                ["tenant_id", parent_column], parent_fk, ondelete="CASCADE", name=op.f(fk_name)
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
            sa.UniqueConstraint("tenant_id", "id", name=op.f(unique_name)),
            sa.UniqueConstraint("tenant_id", parent_column, "external_id", name=op.f(external_unique)),
        )
        op.create_index("ix_" + table + "_tenant_id", table, ["tenant_id"])
        op.create_index(index_name, table, ["tenant_id", parent_column])


def downgrade() -> None:
    op.drop_table("ads")
    op.drop_table("ad_sets")
