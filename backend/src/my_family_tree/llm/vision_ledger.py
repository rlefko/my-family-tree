"""In-process daily spend ledger for vision-LLM calls.

Per-process, in-memory; if a worker process restarts the ledger resets. That is
acceptable for the single-user app where the daily cap is conservative and
worker counts are small. A DB-backed ledger is a follow-up if we ever scale
out."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class VisionLedger:
    cap_usd: float
    _spend: dict[date, float] = field(default_factory=dict)

    def remaining_today(self, today: date) -> float:
        return self.cap_usd - self._spend.get(today, 0.0)

    def under_cap(self, today: date) -> bool:
        return self.remaining_today(today) > 0.0

    def record(self, today: date, usd: float) -> None:
        self._spend[today] = self._spend.get(today, 0.0) + usd

    def spend_today(self, today: date) -> float:
        return self._spend.get(today, 0.0)
