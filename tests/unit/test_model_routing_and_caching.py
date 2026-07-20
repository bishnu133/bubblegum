"""
tests/unit/test_model_routing_and_caching.py
============================================
Task #2 — tiered model routing + prompt caching + call tuning.

Covers:
  * AIConfig.resolved_fast_model / resolved_strong_model fallbacks.
  * get_provider(config, role=...) selects the right model + passes tuning.
  * Anthropic provider applies max_tokens + cacheable system block.
  * OpenAI provider applies max_tokens; caching flag is an accepted no-op.
  * LLMGroundingResolver escalates to the strong provider only when the fast
    result is below the escalate_below threshold.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.models.base import CompletionResult
from bubblegum.core.models.factory import get_provider
from bubblegum.core.grounding.resolvers.llm_grounding import LLMGroundingResolver
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def _cfg(**ai) -> BubblegumConfig:
    base = {"enabled": True, "provider": "anthropic", "model": "base-model"}
    base.update(ai)
    return BubblegumConfig.model_validate({"ai": base})


# --------------------------------------------------------------------------- #
# Config resolution
# --------------------------------------------------------------------------- #

def test_fast_and_strong_default_to_base_model():
    c = _cfg()
    assert c.ai.resolved_fast_model() == "base-model"
    assert c.ai.resolved_strong_model() == "base-model"


def test_fast_and_strong_override_base_model():
    c = _cfg(fast_model="haiku", strong_model="sonnet")
    assert c.ai.resolved_fast_model() == "haiku"
    assert c.ai.resolved_strong_model() == "sonnet"


# --------------------------------------------------------------------------- #
# Factory role selection + tuning propagation
# --------------------------------------------------------------------------- #

def test_factory_role_selects_model_and_passes_tuning():
    c = _cfg(fast_model="haiku", strong_model="sonnet", max_tokens=256, prompt_caching=False)

    fast = get_provider(c, role="fast")
    strong = get_provider(c, role="strong")
    default = get_provider(c, role="default")

    assert fast.model == "haiku"
    assert strong.model == "sonnet"
    assert default.model == "base-model"
    # Tuning flows through to the provider instance.
    assert fast._max_tokens == 256
    assert fast._prompt_caching is False


def test_openai_provider_accepts_tuning():
    c = _cfg(provider="openai", model="gpt-4o-mini", max_tokens=128)
    p = get_provider(c, role="fast")
    assert p.model == "gpt-4o-mini"
    assert p._max_tokens == 128


# --------------------------------------------------------------------------- #
# Anthropic request shape: max_tokens + cacheable system block
# --------------------------------------------------------------------------- #

class _RecordingMessages:
    def __init__(self, sink):
        self._sink = sink

    async def create(self, **kwargs):
        self._sink.update(kwargs)

        class _Usage:
            input_tokens = 5
            output_tokens = 3
            cache_read_input_tokens = 0

        class _Block:
            type = "text"
            text = '{"ref": "role=button[name=\\"OK\\"]", "confidence": 0.9, "reasoning": "x"}'

        class _Resp:
            usage = _Usage()
            content = [_Block()]

        return _Resp()


class _FakeAnthropicClient:
    def __init__(self, sink):
        self.messages = _RecordingMessages(sink)


def test_anthropic_applies_max_tokens_and_cache_control(monkeypatch):
    from bubblegum.core.models import anthropic_provider as ap

    sink: dict = {}
    provider = ap.AnthropicProvider(model="claude-x", api_key="k", max_tokens=321, prompt_caching=True)
    provider._client = _FakeAnthropicClient(sink)  # inject reusable client

    # Import guard inside complete() needs the module importable; stub it.
    monkeypatch.setitem(__import__("sys").modules, "anthropic", type("m", (), {}))

    res = asyncio.run(provider.complete("find OK", system="SYS", response_format="json"))
    assert res.text.startswith("{")
    assert sink["max_tokens"] == 321
    # System sent as a cacheable content block, not a bare string.
    assert isinstance(sink["system"], list)
    assert sink["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_anthropic_plain_system_when_caching_disabled(monkeypatch):
    from bubblegum.core.models import anthropic_provider as ap

    sink: dict = {}
    provider = ap.AnthropicProvider(model="claude-x", api_key="k", prompt_caching=False)
    provider._client = _FakeAnthropicClient(sink)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", type("m", (), {}))

    asyncio.run(provider.complete("find OK", system="SYS"))
    assert isinstance(sink["system"], str)


# --------------------------------------------------------------------------- #
# Escalation
# --------------------------------------------------------------------------- #

class _StubProvider:
    def __init__(self, name, confidence):
        self.provider_name = name
        self.model = name
        self._confidence = confidence
        self.calls = 0

    async def complete(self, prompt, *, system=None, response_format=None):
        self.calls += 1
        # Valid JSON with a quote-free ref so parsing succeeds deterministically.
        return CompletionResult(
            text=f'{{"ref": "text=Go", "confidence": {self._confidence}, "reasoning": "s"}}',
            input_tokens=1, output_tokens=1, model=self.model,
        )


_SNAPSHOT = "- button \"Go\""


def _intent():
    return StepIntent(
        instruction="click Go",
        channel="web",
        platform="chromium",
        action_type="click",
        context={"a11y_snapshot": _SNAPSHOT},
        options=ExecutionOptions(max_cost_level="medium"),
    )


def test_escalation_fires_when_fast_is_weak():
    fast = _StubProvider("fast", 0.55)
    strong = _StubProvider("strong", 0.95)
    r = LLMGroundingResolver()
    r.set_provider(fast, strong=strong, escalate_below=0.70)

    targets = r.resolve(_intent())
    assert strong.calls == 1                      # escalated
    assert targets and targets[0].confidence == pytest.approx(0.95)


def test_no_escalation_when_fast_is_confident():
    fast = _StubProvider("fast", 0.92)
    strong = _StubProvider("strong", 0.95)
    r = LLMGroundingResolver()
    r.set_provider(fast, strong=strong, escalate_below=0.70)

    targets = r.resolve(_intent())
    assert strong.calls == 0                      # fast was good enough
    assert targets and targets[0].confidence == pytest.approx(0.92)


def test_no_escalation_without_strong_provider():
    fast = _StubProvider("fast", 0.40)
    r = LLMGroundingResolver()
    r.set_provider(fast, escalate_below=0.70)     # no strong wired
    r.resolve(_intent())
    assert fast.calls == 1
