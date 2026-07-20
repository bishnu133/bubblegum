"""
tests/unit/test_async_resolver_contract.py
===========================================
Task #5 — async resolver contract.

The GroundingEngine must drive resolvers through resolve_async() so LLM/network
resolvers run natively on the event loop (no throwaway thread + event loop), and
the default resolve_async() must delegate to the sync resolve() with identical
results for deterministic resolvers.
"""

from __future__ import annotations

import asyncio

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.grounding.resolvers.semantic import SemanticResolver
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent


_STRONG_SIGNALS = {
    "text_match": 1.0, "role_match": 1.0, "visibility": 1.0,
    "uniqueness": 1.0, "proximity": 0.5, "memory_history": 0.0,
}


def _target(name="async_only"):
    return ResolvedTarget(
        ref='role=button[name="Go"]',
        confidence=0.9,
        resolver_name=name,
        metadata={"role": "button", "signals": _STRONG_SIGNALS},
    )


def _intent():
    return StepIntent(
        instruction="click Go",
        channel="web",
        action_type="click",
        options=ExecutionOptions(max_cost_level="medium"),
    )


class _AsyncOnlyResolver(Resolver):
    """resolve() would fail — proves the engine takes the async path."""

    name = "async_only"
    priority = 20
    channels = ["web"]
    cost_level = "low"
    tier = 1

    def resolve(self, intent):  # pragma: no cover - must not be called by engine
        raise AssertionError("GroundingEngine must call resolve_async(), not resolve()")

    async def resolve_async(self, intent):
        return [_target(self.name)]


class _SyncResolver(Resolver):
    name = "sync_only"
    priority = 20
    channels = ["web"]
    cost_level = "low"
    tier = 1

    def resolve(self, intent):
        return [_target(self.name)]


def test_engine_drives_resolvers_through_resolve_async():
    reg = ResolverRegistry()
    reg.register(_AsyncOnlyResolver())          # overrides the priority-20 slot
    engine = GroundingEngine(registry=reg)

    target, _traces = asyncio.run(engine.ground(_intent()))
    assert target.ref == 'role=button[name="Go"]'
    assert target.resolver_name == "async_only"


def test_default_resolve_async_delegates_to_sync():
    r = _SyncResolver()
    out = asyncio.run(r.resolve_async(_intent()))
    assert out and out[0].ref == 'role=button[name="Go"]'
    # Identical to the sync path.
    assert out[0].ref == r.resolve(_intent())[0].ref


def test_semantic_resolve_async_dormant_returns_empty():
    # Offloaded path still honours dormancy without touching a thread pool need.
    r = SemanticResolver()
    assert asyncio.run(r.resolve_async(_intent())) == []


def test_semantic_resolve_async_matches_sync_result():
    class _FakeEmb:
        model = "fake"

        def embed(self, texts):
            table = {"Continue": [1.0, 0.0], "Submit": [0.97, 0.24], "Cancel": [0.0, 1.0]}
            return [table.get(t, [0.0, 1.0]) for t in texts]

    snapshot = '- button "Submit"\n- button "Cancel"'
    intent = StepIntent(
        instruction="click Continue",
        channel="web",
        action_type="click",
        target_phrase="Continue",
        context={"a11y_snapshot": snapshot},
        options=ExecutionOptions(max_cost_level="medium"),
    )
    r = SemanticResolver(provider=_FakeEmb(), min_similarity=0.72)
    async_out = asyncio.run(r.resolve_async(intent))
    sync_out = r.resolve(intent)
    assert [t.ref for t in async_out] == [t.ref for t in sync_out]
    assert 'role=button[name="Submit"]' in [t.ref for t in async_out]
