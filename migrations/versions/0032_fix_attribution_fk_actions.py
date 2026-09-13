"""Align nullable attribution foreign keys with domain delete behavior.

Revision ID: 0051_fix_attribution_fk_actions
Revises: 0050_billing_usage_events
"""

from alembic import op


revision = "0051_fix_attribution_fk_actions"
down_revision = "0050_billing_usage_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, columns, referred in (
        ("fk_attributions_tenant_campaign", ["tenant_id", "campaign_id"], ["tenant_id", "id"]),
        ("fk_attributions_tenant_ad_set", ["tenant_id", "ad_set_id"], ["tenant_id", "id"]),
        ("fk_attributions_tenant_ad", ["tenant_id", "ad_id"], ["tenant_id", "id"]),
    ):
        op.drop_constraint(name, "attributions", type_="foreignkey")
        op.create_foreign_key(
            name,
            "attributions",
            {"fk_attributions_tenant_campaign": "campaigns", "fk_attributions_tenant_ad_set": "ad_sets", "fk_attributions_tenant_ad": "ads"}[name],
            columns,
            referred,
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for name, table, columns, referred in (
        ("fk_attributions_tenant_campaign", "campaigns", ["tenant_id", "campaign_id"], ["tenant_id", "id"]),
        ("fk_attributions_tenant_ad_set", "ad_sets", ["tenant_id", "ad_set_id"], ["tenant_id", "id"]),
        ("fk_attributions_tenant_ad", "ads", ["tenant_id", "ad_id"], ["tenant_id", "id"]),
    ):
        op.drop_constraint(name, "attributions", type_="foreignkey")
        op.create_foreign_key(name, "attributions", table, columns, referred, ondelete="RESTRICT")