"""
AI-first grounding (PR3).

When ai_first=True and the AI tier can run, the GroundingEngine attempts the
AI (Tier 3) resolver before the deterministic tiers. When AI cannot run (cost
policy blocks it, or no Tier 3 resolver is eligible), it falls back to the
standard deterministic-first order with no behaviour change.
"""

from __future__ import annotations

import asyncio

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent


class _RecordingResolver(Resolver):
    """A resolver that records when it runs and returns a fixed candidate."""

    def __init__(self, name, priority, tier, channels, confidence, order_log):
        self.name = name
        self.priority = priority
        self.tier = tier
        self.channels = channels
        self.cost_level = "high" if tier == 3 else "low"
        self._confidence = confidence
        self._order_log = order_log

    def resolve(self, intent):
        self._order_log.append(self.name)
        return [
            ResolvedTarget(
                ref=f"{self.name}://1",
                confidence=self._confidence,
                resolver_name=self.name,
                metadata={"element_name": self.name},
            )
        ]


def _intent(max_cost_level="high"):
    return StepIntent(
        instruction="Click login",
        channel="web",
        action_type="click",
        target_phrase="login",
        options=ExecutionOptions(max_cost_level=max_cost_level),
    )


def _registry(order_log, deterministic_conf=0.9, ai_conf=0.9):
    reg = ResolverRegistry()
    reg.register(_RecordingResolver("det", 10, 1, ["web"], deterministic_conf, order_log))
    reg.register(_RecordingResolver("vision", 70, 3, ["web"], ai_conf, order_log))
    return reg


def test_ai_first_runs_ai_tier_before_deterministic():
    order_log: list[str] = []
    engine = GroundingEngine(registry=_registry(order_log), ai_first=True)
    target, _ = asyncio.run(engine.ground(_intent()))
    assert target.resolver_name == "vision"
    assert order_log[0] == "vision"


def test_deterministic_first_by_default():
    order_log: list[str] = []
    engine = GroundingEngine(registry=_registry(order_log), ai_first=False)
    target, _ = asyncio.run(engine.ground(_intent()))
    assert target.resolver_name == "det"
    assert order_log[0] == "det"


def test_ai_first_falls_back_to_deterministic_when_ai_low_confidence():
    order_log: list[str] = []
    # AI returns a low-confidence candidate (below review threshold); the
    # deterministic tier should still win and the AI tier must not block.
    reg = _registry(order_log, deterministic_conf=0.9, ai_conf=0.40)
    engine = GroundingEngine(registry=reg, ai_first=True)
    target, _ = asyncio.run(engine.ground(_intent()))
    assert target.resolver_name == "det"
    assert order_log[0] == "vision"  # AI was tried first


def test_ai_first_noop_when_cost_blocks_ai():
    order_log: list[str] = []
    engine = GroundingEngine(registry=_registry(order_log), ai_first=True)
    # max_cost_level=low blocks the AI tier; with no Tier 3 able to run, the
    # engine resolves deterministically rather than reordering or blocking.
    # (A registry with a Tier 3 resolver + cost=low raises AICostPolicyBlocked
    #  in the standard flow — covered elsewhere — so here we assert the gate
    #  prevents AI-first from changing the order.)
    assert engine._ai_tier_runnable(_intent(max_cost_level="low")) is False
    assert engine._ai_tier_runnable(_intent(max_cost_level="high")) is True
