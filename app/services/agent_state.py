from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class AgentState:
    tenant_id: UUID
    conversation_id: UUID
    contact_id: UUID
    control_version: int
    profile_id: UUID
    profile_version: int
    ai_run_id: UUID | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    intent: str | None = None
    decision: str | None = None
