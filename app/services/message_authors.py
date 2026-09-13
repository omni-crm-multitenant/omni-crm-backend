"""Backward-compatible import location for message author value objects."""

from app.domain.message_authors import (
    AuthorOrigin,
    MessageAuthor,
    validate_message_author_storage,
)

__all__ = ["AuthorOrigin", "MessageAuthor", "validate_message_author_storage"]
