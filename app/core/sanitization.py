from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(
    r"(?:password|passphrase|token|secret|credential|authorization|cookie|api[_-]?key|access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"^Bearer\s+\S+$", re.IGNORECASE),
    re.compile(r"^Basic\s+\S+$", re.IGNORECASE),
    re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"),
    re.compile(r"^(?:EAAB|EAAJ|sk-|pk_live_|rk_live_)[A-Za-z0-9_.-]{8,}$"),
)
EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def _sanitize_string(value: str) -> str:
    if any(pattern.fullmatch(value.strip()) for pattern in SECRET_VALUE_PATTERNS):
        return REDACTED
    value = EMAIL_PATTERN.sub(REDACTED, value)
    return PHONE_PATTERN.sub(REDACTED, value)


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if SENSITIVE_KEY.search(str(key)) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(sanitize_metadata(item) for item in value)
    if isinstance(value, set):
        return sorted((sanitize_metadata(item) for item in value), key=str)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value
