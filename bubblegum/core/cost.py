"""
bubblegum/core/cost.py
======================
Per-run LLM cost accounting + budget hard-stop (X2).

Tier-3 AI calls can surprise on cost. This module turns the token counts every
provider already reports (``CompletionResult.input_tokens`` /
``output_tokens``) into an estimated USD spend, accumulates it for the run, and
exposes a budget check the GroundingEngine consults *before* running Tier 3 —
so once a per-run budget (``grounding.max_run_cost_usd``) is exceeded, further
AI calls are hard-stopped.

A "run" is the process: the tracker is a module-global singleton that
accumulates across steps. ``reset()`` starts a fresh run (the pytest plugin
resets at session start); ``configure_budget()`` sets the ceiling from config.
Pricing is a best-effort per-model table; unknown models estimate at a
conservative default so the budget still bounds spend.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# Approximate USD per 1K tokens (input, output). Best-effort — used only to
# bound spend, not for billing. Unknown models fall back to _DEFAULT_PRICE.
_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic Claude (per 1K tokens)
    "claude-opus-4-8": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5": (0.0008, 0.004),
    # OpenAI
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4.1": (0.005, 0.015),
}
_DEFAULT_PRICE: tuple[float, float] = (0.003, 0.015)


def _price_for(model: str) -> tuple[float, float]:
    key = (model or "").strip().lower()
    if key in _PRICES:
        return _PRICES[key]
    # Prefix match so dated/suffixed model ids still price reasonably.
    for name, price in _PRICES.items():
        if key.startswith(name) or name in key:
            return price
    return _DEFAULT_PRICE


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the USD cost of one completion from its token counts."""
    in_per_1k, out_per_1k = _price_for(model)
    cost = (max(int(input_tokens), 0) / 1000.0) * in_per_1k
    cost += (max(int(output_tokens), 0) / 1000.0) * out_per_1k
    return round(cost, 6)


class CostTracker:
    """Thread-safe accumulator of estimated LLM spend with an optional budget."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spent_usd = 0.0
        self._budget_usd = 0.0  # 0 == disabled (unlimited)
        self._calls = 0

    def configure_budget(self, max_usd: float) -> None:
        with self._lock:
            self._budget_usd = max(float(max_usd or 0.0), 0.0)

    def reset(self) -> None:
        """Start a fresh run: zero the accumulated spend (keeps the budget)."""
        with self._lock:
            self._spent_usd = 0.0
            self._calls = 0

    def record_cost(self, usd: float) -> float:
        with self._lock:
            self._spent_usd += max(float(usd), 0.0)
            self._calls += 1
            return self._spent_usd

    def record_usage(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate + accumulate the cost of one completion; return new total."""
        return self.record_cost(estimate_cost_usd(model, input_tokens, output_tokens))

    @property
    def spent(self) -> float:
        return self._spent_usd

    @property
    def budget(self) -> float:
        return self._budget_usd

    @property
    def calls(self) -> int:
        return self._calls

    def budget_exceeded(self) -> bool:
        """True when a budget is set (>0) and spend has reached/exceeded it."""
        with self._lock:
            return self._budget_usd > 0.0 and self._spent_usd >= self._budget_usd


# Module-global tracker shared by the LLM resolver (records spend) and the
# GroundingEngine (checks the budget before Tier 3).
_TRACKER = CostTracker()


def get_tracker() -> CostTracker:
    return _TRACKER


def configure_budget(max_usd: float) -> None:
    _TRACKER.configure_budget(max_usd)


def reset() -> None:
    _TRACKER.reset()


def record_usage(model: str, input_tokens: int, output_tokens: int) -> float:
    return _TRACKER.record_usage(model, input_tokens, output_tokens)


def spent() -> float:
    return _TRACKER.spent


def budget_exceeded() -> bool:
    return _TRACKER.budget_exceeded()
