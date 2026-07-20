"""
tests/unit/test_llm_grounding_wiring.py
=======================================
Task #1 — the AI grounding tier must actually go live.

Regression guard for the keystone bug: the registry builds LLMGroundingResolver
in stub mode (no provider), and nothing wired a real one, so Tier-3 text
grounding silently returned [] in production. These tests assert:

  1. The resolver exposes set_provider()/has_provider and honours them.
  2. The SDK wires the registered resolver from config (best-effort).
  3. Wiring is a no-op that never raises when AI is disabled / model unset.
  4. cost_level="medium" so the tier is reachable under the default policy.
"""

from __future__ import annotations

import importlib

import pytest

from bubblegum.core.grounding.resolvers.llm_grounding import LLMGroundingResolver


class _FakeProvider:
    provider_name = "fake"
    model = "fake-model"

    async def complete(self, prompt, *, system=None, response_format=None):  # pragma: no cover
        raise NotImplementedError


def test_resolver_provider_setter_toggles_liveness():
    r = LLMGroundingResolver()
    assert r.has_provider is False          # registry stub mode by default
    r.set_provider(_FakeProvider())
    assert r.has_provider is True
    r.set_provider(None)                     # clearing restores stub mode
    assert r.has_provider is False


def test_default_cost_level_is_medium():
    # Reachable under the default max_cost_level="medium" policy — the whole
    # point of wiring the tier. Vision/OCR-image stay "high".
    assert LLMGroundingResolver().cost_level == "medium"


def test_sdk_wiring_stays_dormant_when_provider_cannot_build(monkeypatch):
    # When the provider cannot be built (AI disabled / model unset / SDK or key
    # missing), the tier must stay dormant WITHOUT raising — the deterministic
    # path is never affected.
    import bubblegum.core.sdk as sdk

    monkeypatch.setattr(sdk, "_build_llm_provider", lambda: None)
    try:
        sdk._wire_llm_grounding_provider()  # must not raise
        resolver = sdk._registry.get("llm_grounding")
        assert resolver is not None
        assert resolver.has_provider is False
    finally:
        sdk.configure_llm_provider(None)


def test_build_llm_provider_never_raises_on_bad_config(monkeypatch):
    # Regression guard: a broken get_provider() must be swallowed, not crash a run.
    import bubblegum.core.sdk as sdk

    def _boom(_config):
        raise RuntimeError("provider explosion")

    monkeypatch.setattr("bubblegum.core.models.factory.get_provider", _boom)
    assert sdk._build_llm_provider() is None


def test_configure_llm_provider_injects_and_clears():
    import bubblegum.core.sdk as sdk

    resolver = sdk._registry.get("llm_grounding")
    try:
        sdk.configure_llm_provider(_FakeProvider())
        assert resolver.has_provider is True
        assert sdk._llm_provider is not None
    finally:
        sdk.configure_llm_provider(None)     # restore stub mode for other tests
        assert resolver.has_provider is False


def test_wiring_goes_live_when_provider_builds(monkeypatch):
    import bubblegum.core.sdk as sdk

    monkeypatch.setattr(sdk, "_build_llm_provider", lambda: _FakeProvider())
    try:
        sdk._wire_llm_grounding_provider()
        resolver = sdk._registry.get("llm_grounding")
        assert resolver.has_provider is True
    finally:
        sdk.configure_llm_provider(None)
