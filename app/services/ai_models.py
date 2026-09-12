from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelRegistryError(ValueError):
    pass


class ChatModel(Protocol):
    async def invoke(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class FakeChatModel:
    provider: str = "fake"
    model: str = "fake"

    async def invoke(self, messages: list[dict[str, str]]) -> str:
        return "fake-response"


@dataclass
class ConfiguredChatModel:
    provider: str
    model: str
    api_key: str

    async def invoke(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError(f"{self.provider} adapter is not enabled in this runtime")


SUPPORTED_MODELS: dict[str, frozenset[str]] = {
    "fake": frozenset({"fake"}),
    "openai": frozenset({"gpt-4o-mini", "gpt-4.1-mini"}),
    "anthropic": frozenset({"claude-3-5-sonnet-latest", "claude-3-7-sonnet-latest"}),
}


def get_chat_model(provider: str | Any, model: str | None = None, *, api_key: str | None = None, settings: Any = None) -> ChatModel:
    if model is None:
        profile = provider
        provider = profile.provider
        model = profile.model
    if api_key is None and settings is not None:
        api_key = getattr(settings, f"{provider}_api_key", None)
    models = SUPPORTED_MODELS.get(provider)
    if models is None or model not in models:
        raise ModelRegistryError(f"unsupported model combination: {provider}/{model}")
    if provider == "fake":
        return FakeChatModel()
    if not api_key:
        raise ModelRegistryError(f"missing API key for provider: {provider}")
    return ConfiguredChatModel(provider=provider, model=model, api_key=api_key)
