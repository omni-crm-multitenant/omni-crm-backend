"""Persist one-time Meta OAuth states.

Revision ID: 0016_meta_oauth_states
Revises: 0015_tenant_settings
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0016_meta_oauth_states"
down_revision = "0015_tenant_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "asset_type IN ('whatsapp', 'messenger', 'instagram', 'ad_account')",
            name=op.f("ck_meta_oauth_states_meta_oauth_state_asset_type"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE", name=op.f("fk_meta_oauth_states_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_meta_oauth_states_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meta_oauth_states")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_meta_oauth_states_state_hash")),
    )
    op.create_index(op.f("ix_meta_oauth_states_tenant_id"), "meta_oauth_states", ["tenant_id"])
    op.create_index(op.f("ix_meta_oauth_states_user_id"), "meta_oauth_states", ["user_id"])


def downgrade() -> None:
    op.drop_table("meta_oauth_states")
