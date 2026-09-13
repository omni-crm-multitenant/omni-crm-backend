"""Allow automation as a message author origin.

Revision ID: 0018_message_author_automation
Revises: 0017_contact_identities
"""

from alembic import op


revision = "0018_message_author_automation"
down_revision = "0017_contact_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Naming convention adds ``ck_messages_`` to the logical constraint name.
    op.drop_constraint("message_author_type", "messages", type_="check")
    op.create_check_constraint(
        "message_author_type",
        "messages",
        "author_type IN ('contact', 'user', 'ai', 'automation', 'system')",
    )


def downgrade() -> None:
    op.drop_constraint("message_author_type", "messages", type_="check")
    op.create_check_constraint(
        "message_author_type",
        "messages",
        "author_type IN ('contact', 'user', 'ai', 'system')",
    )
