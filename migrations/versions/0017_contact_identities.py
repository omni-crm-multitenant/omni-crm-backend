"""Add tenant-scoped external contact identities.

Revision ID: 0017_contact_identities
Revises: 0016_meta_oauth_states
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_contact_identities"
down_revision = "0016_meta_oauth_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_channel_assets_tenant_id", "channel_assets", ["tenant_id", "id"])
    op.create_table(
        "contact_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "contact_id"], ["contacts.tenant_id", "contacts.id"], ondelete="CASCADE", name=op.f("fk_contact_identities_tenant_contact")),
        sa.ForeignKeyConstraint(["tenant_id", "channel_asset_id"], ["channel_assets.tenant_id", "channel_assets.id"], ondelete="CASCADE", name=op.f("fk_contact_identities_tenant_asset")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_identities")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_contact_identities_tenant_identity")),
        sa.UniqueConstraint("tenant_id", "channel_asset_id", "external_user_id", name=op.f("uq_contact_identities_tenant_asset_external")),
    )
    op.create_index("ix_contact_identities_tenant_id", "contact_identities", ["tenant_id"])
    op.create_index("ix_contact_identities_contact_id", "contact_identities", ["contact_id"])
    op.create_index("ix_contact_identities_channel_asset_id", "contact_identities", ["channel_asset_id"])


def downgrade() -> None:
    op.drop_table("contact_identities")
    op.drop_constraint("uq_channel_assets_tenant_id", "channel_assets", type_="unique")
