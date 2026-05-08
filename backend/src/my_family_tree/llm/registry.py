"""Provider registry. Holds configured `LLMProvider` instances and resolves
`(provider, model)` for the agent loop."""

from __future__ import annotations

from dataclasses import dataclass

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from my_family_tree.core.config import LLMSettings
from my_family_tree.core.errors import LLMProviderError
from my_family_tree.llm.anthropic_provider import AnthropicProvider
from my_family_tree.llm.base import LLMProvider
from my_family_tree.llm.openai_provider import OpenAIProvider


@dataclass(slots=True)
class ProviderRegistry:
    providers: dict[str, LLMProvider]
    default_provider: str
    default_model: str

    def get(self, name: str | None = None) -> LLMProvider:
        key = name or self.default_provider
        if key not in self.providers:
            raise LLMProviderError(
                f"provider {key!r} not configured (have: {sorted(self.providers)})"
            )
        return self.providers[key]

    def resolve(
        self, *, provider: str | None = None, model: str | None = None
    ) -> tuple[LLMProvider, str]:
        p = self.get(provider)
        return p, model or p.default_model


def build_registry(settings: LLMSettings) -> ProviderRegistry:
    providers: dict[str, LLMProvider] = {}
    if settings.openai_api_key is not None:
        providers["openai"] = OpenAIProvider(
            AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.request_timeout_s,
            ),
            default_model=settings.default_model
            if settings.default_provider == "openai"
            else "gpt-5",
        )
    if settings.anthropic_api_key is not None:
        providers["anthropic"] = AnthropicProvider(
            AsyncAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.request_timeout_s,
            ),
            default_model=settings.default_model
            if settings.default_provider == "anthropic"
            else "claude-opus-4-7",
        )
    if not providers:
        # Allow boot with no key for tests / docs builds. Calls will fail later.
        providers["openai"] = OpenAIProvider(
            AsyncOpenAI(api_key="missing", timeout=settings.request_timeout_s),
            default_model=settings.default_model,
        )
    return ProviderRegistry(
        providers=providers,
        default_provider=settings.default_provider,
        default_model=settings.default_model,
    )
