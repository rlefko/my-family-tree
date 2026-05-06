"""Reasoning effort mapping between providers."""

from __future__ import annotations

from my_family_tree.llm.base import ReasoningEffort

# Anthropic extended thinking budgets in tokens. None disables thinking.
ANTHROPIC_THINKING_BUDGET: dict[ReasoningEffort, int | None] = {
    "none": None,
    "low": 2_000,
    "medium": 8_000,
    "high": 20_000,
    "xhigh": 40_000,
}

# OpenAI Responses API takes the effort string directly. We pass through except
# `xhigh` which maps to `high` if the model doesn't support `xhigh`.
OPENAI_EFFORT_FALLBACKS: dict[ReasoningEffort, str] = {
    "none": "none",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
}
