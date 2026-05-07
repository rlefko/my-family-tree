"""Deep research subagent. Skeleton for v1: spawns an agent run with broader
budgets and web tools, returns proposals for the user to review.

The actual long-running plan/search/extract/propose loop is built on top of
the chat agent loop; we only diverge in budgets, tool capabilities, and the
system prompt."""

from __future__ import annotations

from dataclasses import dataclass

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.system_prompt import CHAT_SYSTEM_PROMPT

DEEP_RESEARCH_SYSTEM_PROMPT = (
    CHAT_SYSTEM_PROMPT
    + "\n\nYou are operating in deep-research mode. You have web_search and "
    + "web_fetch tools and a larger budget. Plan first, then search, then "
    + "verify findings against existing claims, then propose new persons, "
    + "events, and claims. Always cite the URL of any web evidence."
)


@dataclass(slots=True)
class DeepResearchSpec:
    goal: str
    max_tokens: int = 500_000
    max_tool_calls: int = 100
    wall_clock_s: int = 1800

    def budgets(self) -> Budgets:
        return Budgets(
            tokens=self.max_tokens,
            tool_calls=self.max_tool_calls,
            wall_clock_s=self.wall_clock_s,
        )
