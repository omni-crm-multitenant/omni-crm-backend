from __future__ import annotations

import re
from dataclasses import dataclass


INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"(reveal|show|print|dump).{0,40}(system prompt|instructions|api key|token)", re.I),
    re.compile(r"you\s+are\s+now\s+(the|a)\s+", re.I),
    re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions", re.I),
)


@dataclass(frozen=True)
class PromptGuardDecision:
    flagged: bool
    action: str
    reason: str | None = None


def detect_prompt_injection(text: str) -> PromptGuardDecision:
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return PromptGuardDecision(True, "transfer", "instruction_override")
    return PromptGuardDecision(False, "continue")


def redacted_injection_log(text: str) -> dict[str, str]:
    return {"reason": "instruction_override", "message_sha256": __import__("hashlib").sha256(text.encode()).hexdigest()}
