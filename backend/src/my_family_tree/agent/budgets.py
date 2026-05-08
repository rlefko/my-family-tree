"""Budgets bound a single agent run. Exhausting any budget halts the loop."""

from __future__ import annotations

from dataclasses import dataclass

from my_family_tree.core.errors import BudgetExceededError


@dataclass(slots=True)
class Budgets:
    tokens: int = 2_000_000
    tool_calls: int = 500
    wall_clock_s: int = 1800

    def check(self, *, tokens_used: int, tool_calls_used: int) -> None:
        if tokens_used > self.tokens:
            raise BudgetExceededError(f"token budget {self.tokens} exhausted")
        if tool_calls_used > self.tool_calls:
            raise BudgetExceededError(f"tool-call budget {self.tool_calls} exhausted")
