from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GraphCheckpoint(Base):
    __tablename__ = "graph_checkpoints"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "conversation_id"], ["conversations.tenant_id", "conversations.id"], ondelete="CASCADE", name="fk_graph_checkpoints_tenant_conversation"),
    )

    tenant_id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
