from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiUsageLedger(Base):
    __tablename__ = "ai_usage_ledgers"
    __table_args__ = (UniqueConstraint("tenant_id", "month", name="uq_ai_usage_tenant_month"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    reserved_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    consumed_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
