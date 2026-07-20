"""
tests/unit/test_semantic_resolver.py
=====================================
Task #4 — embedding-based semantic Tier-2 resolver + cache.

Covers dormancy (safe default), cache batching, cosine, the factory, the
resolver's match/threshold behaviour, and the SDK injection hook (incl. the
callable escape hatch for offline embeddings).
"""

from __future__ import annotations

import math

import pytest

from bubblegum.core import embedding_cache
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.models.embeddings import (
    CallableEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)
from bubblegum.core.grounding.resolvers.semantic import SemanticResolver
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# --------------------------------------------------------------------------- #
# A deterministic fake embedding provider
# --------------------------------------------------------------------------- #

class _FakeEmbeddings:
    """Maps known strings to fixed unit-ish vectors; counts embed() calls."""

    model = "fake-embed"

    def __init__(self, table: dict[str, list[float]]):
        self._table = table
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [self._table.get(t, [0.0, 0.0, 1.0]) for t in texts]


_TABLE = {
    "Continue":       [1.0, 0.0, 0.0],
    "Submit":         [0.96, 0.28, 0.0],   # cosine ~0.96 with Continue
    "Cancel":         [0.0, 1.0, 0.0],     # cosine 0.0
    "Create account": [0.30, 0.0, 0.95],
}


def _intent(target_phrase, snapshot, action="click"):
    return StepIntent(
        instruction=f"{action} {target_phrase}",
        channel="web",
        platform="chromium",
        action_type=action,
        target_phrase=target_phrase,
        context={"a11y_snapshot": snapshot},
        options=ExecutionOptions(max_cost_level="medium"),
    )


_SNAPSHOT = '- button "Submit"\n- button "Cancel"\n- link "Create account"'


# --------------------------------------------------------------------------- #
# Dormancy — safe default
# --------------------------------------------------------------------------- #

def test_dormant_without_provider():
    r = SemanticResolver()
    assert r.has_provider is False
    assert r.supports(_intent("Continue", _SNAPSHOT)) is False
    assert r.resolve(_intent("Continue", _SNAPSHOT)) == []


# --------------------------------------------------------------------------- #
# Cache + cosine
# --------------------------------------------------------------------------- #

def test_embed_cached_batches_and_caches():
    embedding_cache.reset()
    p = _FakeEmbeddings(_TABLE)
    v1 = embedding_cache.embed_cached(p, ["Continue", "Submit"])
    assert p.calls == 1                       # one batched call
    v2 = embedding_cache.embed_cached(p, ["Continue", "Submit"])
    assert p.calls == 1                       # fully cached — no new call
    assert v1 == v2
    # A new text triggers exactly one more call, only for the miss.
    embedding_cache.embed_cached(p, ["Continue", "Cancel"])
    assert p.calls == 2


def test_cosine_edge_cases():
    assert embedding_cache.cosine(None, [1, 2]) == 0.0
    assert embedding_cache.cosine([1, 2], [1, 2, 3]) == 0.0
    assert embedding_cache.cosine([0, 0], [1, 1]) == 0.0
    assert embedding_cache.cosine([1, 0], [1, 0]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def _cfg(**ai):
    base = {"enabled": True, "provider": "openai", "model": "gpt-4o-mini"}
    base.update(ai)
    return BubblegumConfig.model_validate({"ai": base})


def test_factory_none_without_embedding_model():
    assert get_embedding_provider(_cfg()) is None


def test_factory_builds_openai_provider():
    p = get_embedding_provider(_cfg(embedding_model="text-embedding-3-small"))
    assert isinstance(p, OpenAIEmbeddingProvider)
    assert p.model == "text-embedding-3-small"


def test_factory_none_for_provider_without_backend():
    # anthropic has no built-in embeddings backend -> dormant (inject instead)
    assert get_embedding_provider(_cfg(provider="anthropic", embedding_model="x")) is None


# --------------------------------------------------------------------------- #
# Resolver matching
# --------------------------------------------------------------------------- #

def test_semantic_matches_above_threshold_only():
    embedding_cache.reset()
    r = SemanticResolver(provider=_FakeEmbeddings(_TABLE), min_similarity=0.72)
    targets = r.resolve(_intent("Continue", _SNAPSHOT))
    refs = [t.ref for t in targets]
    # "Submit" (~0.96) is emitted; "Cancel" (0.0) and "Create account" (low) are not.
    assert 'role=button[name="Submit"]' in refs
    assert all("Cancel" not in ref for ref in refs)
    top = targets[0]
    assert top.metadata["source"] == "semantic"
    assert top.metadata["semantic_similarity"] >= 0.72
    assert "signals" in top.metadata


def test_semantic_returns_empty_on_no_labels():
    r = SemanticResolver(provider=_FakeEmbeddings(_TABLE))
    assert r.resolve(_intent("Continue", "   ")) == []


def test_semantic_degrades_on_provider_error():
    class _Boom:
        model = "boom"

        def embed(self, texts):
            raise RuntimeError("embedding service down")

    r = SemanticResolver(provider=_Boom())
    # Never raises — returns [] so the LLM tier can take over.
    assert r.resolve(_intent("Continue", _SNAPSHOT)) == []


# --------------------------------------------------------------------------- #
# SDK injection hook
# --------------------------------------------------------------------------- #

def test_configure_embedding_provider_wraps_callable():
    import bubblegum.core.sdk as sdk

    def fake_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    try:
        sdk.configure_embedding_provider(fake_embed)
        resolver = sdk._registry.get("semantic")
        assert resolver.has_provider is True
        assert isinstance(sdk._embedding_provider, CallableEmbeddingProvider)
    finally:
        sdk.configure_embedding_provider(None)
        assert sdk._registry.get("semantic").has_provider is False
