"""
tests/unit/test_provider_resilience_and_pricing.py
==================================================
Task #7 — provider hardening + consolidation.

Covers the shared fence-strip (single source), the retry/timeout wrapper,
config-driven pricing, and that the resilience wrapper is actually applied
inside the Anthropic/OpenAI providers.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core import cost
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.models._shared import strip_code_fence
from bubblegum.core.models.resilience import call_with_resilience, is_transient_error


# --------------------------------------------------------------------------- #
# Shared fence strip is the single source
# --------------------------------------------------------------------------- #

def test_fence_strip_single_source():
    import bubblegum.core.models.anthropic_provider as ta
    import bubblegum.core.vision.backends.anthropic as va
    assert ta._strip_code_fence is strip_code_fence
    assert va._strip_code_fence is strip_code_fence


def test_fence_strip_behaviour():
    assert strip_code_fence("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert strip_code_fence('{"b": 2}') == '{"b": 2}'
    assert strip_code_fence("") == ""


# --------------------------------------------------------------------------- #
# Resilience
# --------------------------------------------------------------------------- #

def test_is_transient_classification():
    assert is_transient_error(TimeoutError()) is True
    assert is_transient_error(ConnectionError()) is True
    assert is_transient_error(RuntimeError("Rate limit exceeded")) is True
    assert is_transient_error(RuntimeError("503 Service Unavailable")) is True
    assert is_transient_error(ValueError("invalid request")) is False

    class _E(Exception):
        status_code = 429
    assert is_transient_error(_E()) is True


def test_retries_transient_then_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("overloaded")
        return "ok"

    out = asyncio.run(call_with_resilience(flaky, timeout_s=5, max_retries=3, backoff_ms=0))
    assert out == "ok" and calls["n"] == 3


def test_gives_up_after_max_retries():
    calls = {"n": 0}

    async def always_429():
        calls["n"] += 1
        raise RuntimeError("429 too many requests")

    with pytest.raises(RuntimeError):
        asyncio.run(call_with_resilience(always_429, timeout_s=5, max_retries=2, backoff_ms=0))
    assert calls["n"] == 3   # first + 2 retries


def test_no_retry_on_deterministic_error():
    calls = {"n": 0}

    async def bad():
        calls["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        asyncio.run(call_with_resilience(bad, timeout_s=5, max_retries=3, backoff_ms=0))
    assert calls["n"] == 1


def test_hard_timeout_is_transient_and_retried():
    calls = {"n": 0}

    async def slow():
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(1.0)     # exceeds timeout on first attempt
        return "recovered"

    out = asyncio.run(call_with_resilience(slow, timeout_s=0.05, max_retries=1, backoff_ms=0))
    assert out == "recovered" and calls["n"] == 2


# --------------------------------------------------------------------------- #
# Config-driven pricing
# --------------------------------------------------------------------------- #

def test_pricing_override_beats_builtin():
    try:
        cost.configure_pricing({"claude-haiku-4-5": [1.0, 2.0]})
        # 1000 in + 1000 out -> 1.0 + 2.0
        assert cost.estimate_cost_usd("claude-haiku-4-5", 1000, 1000) == pytest.approx(3.0)
    finally:
        cost.configure_pricing({})


def test_pricing_falls_back_to_builtin_when_no_override():
    cost.configure_pricing({})
    # built-in gpt-4o-mini price (0.00015, 0.0006)
    assert cost.estimate_cost_usd("gpt-4o-mini", 1000, 1000) == pytest.approx(0.00075)


def test_malformed_pricing_is_ignored():
    try:
        cost.configure_pricing({"x": ["bad"], "y": [0.001, 0.002]})
        assert cost.estimate_cost_usd("y", 1000, 0) == pytest.approx(0.001)
        # 'x' was skipped -> default pricing used, no crash
        cost.estimate_cost_usd("x", 1000, 1000)
    finally:
        cost.configure_pricing({})


def test_config_pricing_flows_through_factory():
    c = BubblegumConfig.model_validate({
        "ai": {"enabled": True, "provider": "openai", "model": "gpt-4o-mini",
               "timeout_ms": 12345, "max_retries": 5, "retry_backoff_ms": 250},
    })
    from bubblegum.core.models.factory import get_provider
    p = get_provider(c, role="fast")
    assert p._timeout_s == pytest.approx(12.345)
    assert p._max_retries == 5
    assert p._backoff_ms == 250


# --------------------------------------------------------------------------- #
# Providers actually apply the wrapper
# --------------------------------------------------------------------------- #

def test_anthropic_retries_via_resilience(monkeypatch):
    from bubblegum.core.models import anthropic_provider as ap

    monkeypatch.setitem(__import__("sys").modules, "anthropic", type("m", (), {}))

    attempts = {"n": 0}

    class _Messages:
        async def create(self, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("overloaded_error")

            class _Usage:
                input_tokens = 1
                output_tokens = 1
                cache_read_input_tokens = 0

            class _Block:
                type = "text"
                text = '{"ok": true}'

            class _Resp:
                usage = _Usage()
                content = [_Block()]

            return _Resp()

    class _Client:
        messages = _Messages()

    p = ap.AnthropicProvider(model="claude-x", api_key="k", max_retries=2, retry_backoff_ms=0)
    p._client = _Client()
    res = asyncio.run(p.complete("hi"))
    assert attempts["n"] == 2          # retried once
    assert res.text == '{"ok": true}'
