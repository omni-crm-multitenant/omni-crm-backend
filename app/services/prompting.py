from __future__ import annotations

from collections.abc import Iterable
from app.services.prompt_guard import detect_prompt_injection


def assemble_agent_messages(*, instructions: str, client_messages: Iterable[str | dict]) -> list[dict[str, str]]:
    """Keep trusted profile instructions in system role and client data in user role."""
    messages = [{"role": "system", "content": instructions}]
    for item in client_messages:
        content = item if isinstance(item, str) else str(item.get("content", ""))
        messages.append({"role": "user", "content": content})
    return messages


def guard_client_message(text: str) -> tuple[list[dict[str, str]], object]:
    decision = detect_prompt_injection(text)
    return [{"role": "user", "content": text}], decision
