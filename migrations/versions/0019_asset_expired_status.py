"""Allow expired channel assets.

Revision ID: 0019_asset_expired_status
Revises: 0018_message_author_automation
"""

from alembic import op


revision = "0019_asset_expired_status"
down_revision = "0018_message_author_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("channel_asset_status", "channel_assets", type_="check")
    op.create_check_constraint(
        "channel_asset_status",
        "channel_assets",
        "status IN ('connected', 'disconnected', 'expired', 'error')",
    )


def downgrade() -> None:
    op.drop_constraint("channel_asset_status", "channel_assets", type_="check")
    op.create_check_constraint(
        "channel_asset_status",
        "channel_assets",
        "status IN ('connected', 'disconnected', 'error')",
    )
