"""Harden email uniqueness and membership roles.

Revision ID: 0005_identity_constraints
Revises: 0004_email_verification
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_identity_constraints"
down_revision = "0004_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.drop_constraint(op.f("ck_memberships_membership_role"), "memberships", type_="check")
    op.execute("UPDATE memberships SET role = 'agente_comercial' WHERE role = 'agente'")
    op.create_check_constraint(
        op.f("ck_memberships_membership_role"),
        "memberships",
        "role IN ('administrador', 'supervisor', 'agente_comercial')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_memberships_membership_role"), "memberships", type_="check")
    op.execute("UPDATE memberships SET role = 'agente' WHERE role = 'agente_comercial'")
    op.create_check_constraint(
        op.f("ck_memberships_membership_role"),
        "memberships",
        "role IN ('administrador', 'supervisor', 'agente')",
    )
    op.drop_index("uq_users_email_lower", table_name="users")
