from typing import Any
from uuid import UUID

from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, MetaData, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantScopedMixin:
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def tenant_reference_constraint(
    local_column: str,
    remote_table: str,
    *,
    ondelete: str = "RESTRICT",
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["tenant_id", local_column],
        [f"{remote_table}.tenant_id", f"{remote_table}.id"],
        ondelete=ondelete,
    )


def tenant_identity_constraint(*, table_name: str) -> UniqueConstraint:
    """Return standard composite identity constraint for tenant-scoped rows."""
    return UniqueConstraint("tenant_id", "id", name=f"uq_{table_name}_tenant_identity")


def model_metadata() -> Any:
    return Base.metadata
