from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pipelines_tenant_identity"),
        Index("ix_pipelines_tenant_default", "tenant_id", "is_default"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_pipeline_stages_tenant_identity"),
        UniqueConstraint("tenant_id", "pipeline_id", "position", name="uq_pipeline_stages_tenant_pipeline_position"),
        CheckConstraint("terminal_type IN ('none', 'won', 'lost')", name="pipeline_stage_terminal_type"),
        ForeignKeyConstraint(
            ["tenant_id", "pipeline_id"],
            ["pipelines.tenant_id", "pipelines.id"],
            ondelete="CASCADE",
            name="fk_pipeline_stages_tenant_pipeline",
        ),
        Index("ix_pipeline_stages_tenant_pipeline", "tenant_id", "pipeline_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    pipeline_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    terminal_type: Mapped[str] = mapped_column(String(10), nullable=False, default="none", server_default="none")
    ai_can_transition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
