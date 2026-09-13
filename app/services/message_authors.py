from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class AuthorOrigin(StrEnum):
    CONTACT = "contact"
    AGENT = "agent"
    AI = "ai"
    AUTOMATION = "automation"
    SYSTEM = "system"


@dataclass(frozen=True)
class MessageAuthor:
    origin: AuthorOrigin
    source_id: UUID | None = None
    user_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.origin is AuthorOrigin.AGENT and self.user_id is None:
            raise ValueError("agent author requires user_id")
        if self.origin is not AuthorOrigin.AGENT and self.user_id is not None:
            raise ValueError("only agent author may carry user_id")
        if self.origin in {AuthorOrigin.CONTACT, AuthorOrigin.AI, AuthorOrigin.AUTOMATION, AuthorOrigin.SYSTEM} and self.source_id is None:
            raise ValueError(f"{self.origin.value} author requires source_id")

    @classmethod
    def contact(cls, identity_id: UUID) -> "MessageAuthor":
        return cls(AuthorOrigin.CONTACT, source_id=identity_id)

    @classmethod
    def agent(cls, user_id: UUID) -> "MessageAuthor":
        return cls(AuthorOrigin.AGENT, user_id=user_id)

    @classmethod
    def ai(cls, run_id: UUID) -> "MessageAuthor":
        return cls(AuthorOrigin.AI, source_id=run_id)

    @classmethod
    def automation(cls, action_id: UUID) -> "MessageAuthor":
        return cls(AuthorOrigin.AUTOMATION, source_id=action_id)

    @classmethod
    def system(cls, event_id: UUID) -> "MessageAuthor":
        return cls(AuthorOrigin.SYSTEM, source_id=event_id)

    def storage_fields(self) -> dict[str, object]:
        author_type = "user" if self.origin is AuthorOrigin.AGENT else self.origin.value
        fields: dict[str, object] = {"author_type": author_type, "author_user_id": self.user_id}
        if self.source_id is not None:
            fields["message_metadata"] = {
                "author_origin": self.origin.value,
                "author_source_id": str(self.source_id),
            }
        return fields


def validate_message_author_storage(author_type: str, author_user_id: UUID | None, metadata: dict) -> None:
    allowed = {"contact", "user", "ai", "automation", "system"}
    if author_type not in allowed:
        raise ValueError("invalid author_type")
    if author_type == "user":
        if author_user_id is None or metadata.get("author_origin") not in {None, "agent"}:
            raise ValueError("user author requires agent user_id")
    elif author_user_id is not None:
        raise ValueError("only user author may carry author_user_id")
