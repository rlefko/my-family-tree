"""Conflict resolver subagent. Given a conflict ID, fetches both sides, runs
the agent loop with PROPOSE capability, and produces a single
`proposal(action='resolve_conflict')` for the user to approve."""

from __future__ import annotations

from dataclasses import dataclass

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.system_prompt import CHAT_SYSTEM_PROMPT

CONFLICT_RESOLVER_SYSTEM_PROMPT = (
    CHAT_SYSTEM_PROMPT
    + "\n\nYou are resolving a specific conflict. Read both sides via "
    + "`conflict_get`, fetch supporting evidence via `claim_search` and "
    + "`hybrid_search`, then call `conflict_propose_resolution` exactly once. "
    + "Do not approve the proposal yourself; the user will review."
)


@dataclass(slots=True)
class ConflictResolverSpec:
    conflict_id: str
    max_tokens: int = 1_000_000
    max_tool_calls: int = 150

    def budgets(self) -> Budgets:
        return Budgets(tokens=self.max_tokens, tool_calls=self.max_tool_calls)
