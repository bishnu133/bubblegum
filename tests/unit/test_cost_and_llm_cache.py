"""Unit tests for cost budget hard-stop + LLM decision cache (X2).

Covers cost estimation + the per-run CostTracker budget, the LLM decision cache,
the LLM resolver's cache-replay + cost accounting, and the GroundingEngine's
Tier-3 budget hard-stop.
"""

from __future__ import annotations

import pytest

from bubblegum.core import cost, llm_cache
from bubblegum.core.cost import CostTracker, estimate_cost_usd
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import AICostPolicyBlockedError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolvers.llm_grounding import LLMGroundingResolver
from bubblegum.core.models.base import CompletionResult
from bubblegum.core.schemas import ExecutionOptions, StepIntent


@pytest.fixture(autouse=True)
def _isolate_global_state():
    """Reset the process-global cost tracker + LLM cache around each test."""
    cost.reset()
    cost.configure_budget(0.0)
    llm_cache.reset()
    yield
    cost.reset()
    cost.configure_budget(0.0)
    llm_cache.reset()


# ---------------------------------------------------------------------------
# Cost estimation + tracker
# ---------------------------------------------------------------------------


def test_estimate_cost_known_and_unknown_model():
    # 1000 in + 1000 out at opus prices (0.015 / 0.075 per 1k) = 0.015 + 0.075.
    assert estimate_cost_usd("claude-opus-4-8", 1000, 1000) == pytest.approx(0.090)
    # Unknown model → default price (0.003 / 0.015), still bounded.
    assert estimate_cost_usd("some-unknown-model", 1000, 1000) == pytest.approx(0.018)
    assert estimate_cost_usd("anything", 0, 0) == 0.0


def test_cost_tracker_budget_and_reset():
    t = CostTracker()
    assert t.budget_exceeded() is False        # no budget configured
    t.configure_budget(0.05)
    t.record_usage("claude-opus-4-8", 100, 100)  # ~0.009
    assert t.budget_exceeded() is False
    t.record_usage("claude-opus-4-8", 1000, 1000)  # +0.09 → over 0.05
    assert t.budget_exceeded() is True
    assert t.calls == 2
    t.reset()
    assert t.spent == 0.0
    assert t.budget_exceeded() is False         # budget kept, spend cleared


# ---------------------------------------------------------------------------
# LLM decision cache
# ---------------------------------------------------------------------------


def _intent(instruction="Click Login", screen_sig="scr-1", action="click"):
    return StepIntent(
        instruction=instruction,
        channel="web",
        platform="web",
        action_type=action,
        target_phrase=instruction,
        context={"screen_signature": screen_sig, "a11y_snapshot": '- button "Login"'},
        options=ExecutionOptions(max_cost_level="high"),
    )


def test_llm_cache_key_requires_screen_signature():
    assert llm_cache.make_key(_intent(screen_sig="")) is None
    key = llm_cache.make_key(_intent(screen_sig="scr-1"))
    assert key and "scr-1" in key
    # Same screen+action+phrase → same key regardless of case/spacing.
    assert key == llm_cache.make_key(_intent(instruction="click   login"))


def test_llm_cache_get_put_returns_copies():
    from bubblegum.core.schemas import ResolvedTarget

    key = "k"
    target = ResolvedTarget(ref="role=button[name=\"Login\"]", confidence=0.9, resolver_name="llm_grounding")
    llm_cache.put(key, [target])
    got = llm_cache.get(key)
    assert got and got[0].ref == target.ref
    got[0].metadata["mutated"] = True            # mutate the copy
    assert "mutated" not in llm_cache.get(key)[0].metadata   # cache intact
    assert llm_cache.stats()["hits"] >= 2


# ---------------------------------------------------------------------------
# LLM resolver: cache replay + cost accounting
# ---------------------------------------------------------------------------


class _CountingProvider:
    provider_name = "fake"
    model = "claude-opus-4-8"

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, *, system=None, response_format=None, json_schema=None):
        self.calls += 1
        return CompletionResult(
            text='{"ref": "role=button[name=\\"Login\\"]", "confidence": 0.91}',
            input_tokens=500,
            output_tokens=50,
            provider="fake",
            model="claude-opus-4-8",
        )


@pytest.mark.asyncio
async def test_resolver_caches_decision_and_records_cost():
    provider = _CountingProvider()
    resolver = LLMGroundingResolver(provider=provider)

    first = await resolver.resolve_async(_intent())
    assert first and first[0].ref.startswith("role=button")
    assert provider.calls == 1
    assert cost.spent() > 0.0
    spent_after_first = cost.spent()

    # Same screen + instruction → cache hit, no second model call, no extra spend.
    second = await resolver.resolve_async(_intent())
    assert second and second[0].ref == first[0].ref
    assert provider.calls == 1                    # NOT called again
    assert cost.spent() == spent_after_first

    # A different screen signature misses the cache → model called again.
    await resolver.resolve_async(_intent(screen_sig="scr-2"))
    assert provider.calls == 2


# ---------------------------------------------------------------------------
# Engine Tier-3 budget hard-stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_blocks_tier3_when_budget_exceeded():
    cost.configure_budget(0.01)
    cost.record_usage("claude-opus-4-8", 1000, 1000)  # ~0.09 > 0.01
    assert cost.budget_exceeded()

    engine = GroundingEngine(
        registry=ResolverRegistry(),
        accept_threshold=0.85,
        review_threshold=0.70,
        ambiguous_gap=0.05,
        reject_threshold=0.50,
    )
    # No a11y context → tiers 1/2 find nothing, Tier 3 would run but is blocked.
    intent = StepIntent(
        instruction="Click Login",
        channel="web",
        platform="web",
        action_type="click",
        target_phrase="Login",
        options=ExecutionOptions(max_cost_level="high"),
    )
    with pytest.raises(AICostPolicyBlockedError, match="budget exceeded"):
        await engine.ground(intent)


@pytest.mark.asyncio
async def test_engine_allows_tier3_when_budget_not_set():
    # Budget disabled (0) → no hard-stop even with prior spend recorded.
    cost.configure_budget(0.0)
    cost.record_usage("claude-opus-4-8", 1000, 1000)
    assert cost.budget_exceeded() is False
