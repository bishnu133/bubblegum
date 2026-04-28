"""
tests/unit/test_phase2.py
==========================
Phase 2 unit tests — ModelProvider abstraction, LLMGroundingResolver,
CandidateRanker signal formula, and factory wiring.

All tests are self-contained with mocks — no real API keys required.
Run with: pytest tests/unit/test_phase2.py -v
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bubblegum.core.models.base import CompletionResult, ModelProvider
from bubblegum.core.models.openai_provider import OpenAIProvider
from bubblegum.core.models.anthropic_provider import AnthropicProvider
from bubblegum.core.models.local_provider import LocalProvider
from bubblegum.core.models.factory import get_provider
from bubblegum.core.grounding.resolvers.llm_grounding import (
    LLMGroundingResolver,
    _filter_snapshot,
    _parse_response,
    _build_prompt,
)
from bubblegum.core.grounding.ranker import CandidateRanker, compute_confidence
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent
from bubblegum.core.config import BubblegumConfig, AIConfig
from bubblegum.core.grounding.errors import ProviderConfigError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent(
    instruction: str = "Click Login",
    action_type: str = "click",
    context: dict | None = None,
    max_cost_level: str = "high",
) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel="web",
        platform="web",
        action_type=action_type,
        context=context or {},
        options=ExecutionOptions(max_cost_level=max_cost_level),
    )


def _make_result(text: str, tokens: int = 10) -> CompletionResult:
    return CompletionResult(
        text=text,
        input_tokens=tokens,
        output_tokens=20,
        latency_ms=150,
        provider="openai",
        model="gpt-4o-mini",
    )


def _mock_provider(response_text: str) -> ModelProvider:
    """Return a mock ModelProvider that returns response_text from complete()."""
    provider = MagicMock(spec=ModelProvider)
    provider.provider_name = "mock"
    provider.model = "mock-model"
    provider.complete = AsyncMock(return_value=_make_result(response_text))
    return provider


SAMPLE_SNAPSHOT = """\
- banner
  - link "Home"
- main
  - heading "Login"
  - textbox "Username"
  - textbox "Password"
  - button "Sign In"
  - button "Cancel"
  - link "Forgot password"
"""


# ===========================================================================
# 1. ModelProvider ABC
# ===========================================================================

class TestModelProviderABC:
    def test_completion_result_fields(self):
        r = CompletionResult(
            text="hello",
            input_tokens=5,
            output_tokens=3,
            latency_ms=100,
            provider="openai",
            model="gpt-4o-mini",
        )
        assert r.text == "hello"
        assert r.input_tokens == 5
        assert r.provider == "openai"

    def test_completion_result_defaults(self):
        r = CompletionResult(text="hi")
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.latency_ms == 0

    def test_model_provider_is_abstract(self):
        """Cannot instantiate ModelProvider directly."""
        with pytest.raises(TypeError):
            ModelProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_complete(self):
        class BrokenProvider(ModelProvider):
            pass   # missing complete()

        with pytest.raises(TypeError):
            BrokenProvider()

    def test_log_call_emits_safe_fields(self, caplog):
        """_log_call writes safe metadata and does NOT write prompt text."""
        provider = OpenAIProvider(model="gpt-4o-mini")
        with caplog.at_level(logging.INFO, logger="bubblegum.core.models.base"):
            provider._log_call(
                input_tokens=42,
                output_tokens=17,
                latency_ms=200,
                payload_type="text+json",
                redacted=True,
            )
        log_text = caplog.text
        assert "openai" in log_text
        assert "gpt-4o-mini" in log_text
        assert "42" in log_text
        assert "200" in log_text
        # Raw prompt must NEVER appear — we only logged metadata
        assert "prompt" not in log_text.lower() or "raw" not in log_text.lower()


# ===========================================================================
# 2. OpenAIProvider
# ===========================================================================

class TestOpenAIProvider:
    def test_requires_model(self):
        with pytest.raises(ValueError, match="model"):
            OpenAIProvider(model="")

    def test_provider_name(self):
        p = OpenAIProvider(model="gpt-4o-mini")
        assert p.provider_name == "openai"
        assert p.model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_complete_sends_messages_and_parses_response(self):
        """Mock AsyncOpenAI — verify message structure and response parsing."""
        fake_response = MagicMock()
        fake_response.choices[0].message.content = '{"ref": "role=button[name=\\"Login\\"]", "confidence": 0.95}'
        fake_response.usage.prompt_tokens = 30
        fake_response.usage.completion_tokens = 15

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        provider = OpenAIProvider(model="gpt-4o-mini")
        provider._client = mock_client

        result = await provider.complete(
            "Click Login",
            system="You are a tester.",
            response_format="json",
        )

        assert result.text == '{"ref": "role=button[name=\\"Login\\"]", "confidence": 0.95}'
        assert result.input_tokens == 30
        assert result.output_tokens == 15
        assert result.provider == "openai"
        assert result.model == "gpt-4o-mini"

        # Verify the call included json response_format
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_complete_includes_system_message(self):
        fake_response = MagicMock()
        fake_response.choices[0].message.content = "ok"
        fake_response.usage.prompt_tokens = 10
        fake_response.usage.completion_tokens = 2

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        provider = OpenAIProvider(model="gpt-4o-mini")
        provider._client = mock_client

        await provider.complete("hi", system="You are a helper.")

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles

    @pytest.mark.asyncio
    async def test_raw_payload_not_logged(self, caplog):
        """Confirm prompt text never appears in logs."""
        fake_response = MagicMock()
        fake_response.choices[0].message.content = "done"
        fake_response.usage.prompt_tokens = 5
        fake_response.usage.completion_tokens = 2

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        provider = OpenAIProvider(model="gpt-4o-mini", log_calls=True)
        provider._client = mock_client

        secret_prompt = "SUPERSECRET_PROMPT_CONTENT_XYZ"
        with caplog.at_level(logging.DEBUG):
            await provider.complete(secret_prompt)

        assert secret_prompt not in caplog.text

    @pytest.mark.asyncio
    async def test_complete_without_response_format(self):
        fake_response = MagicMock()
        fake_response.choices[0].message.content = "plain text"
        fake_response.usage.prompt_tokens = 5
        fake_response.usage.completion_tokens = 3

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        provider = OpenAIProvider(model="gpt-4o-mini")
        provider._client = mock_client

        result = await provider.complete("What is 2+2?")
        assert result.text == "plain text"

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "response_format" not in call_kwargs


# ===========================================================================
# 3. Stub providers
# ===========================================================================

class TestStubProviders:
    @pytest.mark.asyncio
    async def test_anthropic_stub_raises(self):
        p = AnthropicProvider(model="claude-sonnet-latest")
        with pytest.raises(NotImplementedError, match="Phase 2 stub"):
            await p.complete("hello")

    @pytest.mark.asyncio
    async def test_local_stub_raises(self):
        p = LocalProvider(model="llama3")
        with pytest.raises(NotImplementedError, match="Phase 2 stub"):
            await p.complete("hello")

    def test_anthropic_requires_model(self):
        with pytest.raises(ValueError):
            AnthropicProvider(model="")

    def test_local_requires_model(self):
        with pytest.raises(ValueError):
            LocalProvider(model="")


# ===========================================================================
# 4. Factory
# ===========================================================================

class TestGetProvider:
    def _config(self, provider: str, model: str, enabled: bool = True) -> BubblegumConfig:
        cfg = BubblegumConfig()
        cfg.ai.enabled = enabled
        cfg.ai.provider = provider
        cfg.ai.model = model
        return cfg

    def test_openai_provider_returned(self):
        cfg = self._config("openai", "gpt-4o-mini")
        p = get_provider(cfg)
        assert isinstance(p, OpenAIProvider)
        assert p.model == "gpt-4o-mini"

    def test_anthropic_stub_returned(self):
        cfg = self._config("anthropic", "claude-sonnet-latest")
        p = get_provider(cfg)
        assert isinstance(p, AnthropicProvider)

    def test_local_stub_returned(self):
        cfg = self._config("local", "llama3")
        p = get_provider(cfg)
        assert isinstance(p, LocalProvider)

    def test_ai_disabled_raises(self):
        cfg = self._config("openai", "gpt-4o-mini", enabled=False)
        with pytest.raises(ProviderConfigError, match="disabled"):
            get_provider(cfg)

    def test_missing_model_raises(self):
        cfg = BubblegumConfig()
        cfg.ai.enabled = True
        cfg.ai.provider = "openai"
        cfg.ai.model = None
        with pytest.raises(ProviderConfigError, match="model"):
            get_provider(cfg)

    def test_unknown_provider_raises(self):
        cfg = self._config("fakeprovider", "some-model")
        with pytest.raises(ProviderConfigError, match="Unknown"):
            get_provider(cfg)

    def test_gemini_not_implemented_raises(self):
        cfg = self._config("gemini", "gemini-pro")
        with pytest.raises(ProviderConfigError, match="Gemini"):
            get_provider(cfg)


# ===========================================================================
# 5. Snapshot filtering
# ===========================================================================

class TestFilterSnapshot:
    def test_click_keeps_buttons_and_links(self):
        filtered = _filter_snapshot(SAMPLE_SNAPSHOT, "click")
        assert "button" in filtered
        assert "link" in filtered
        assert "textbox" not in filtered
        assert "heading" not in filtered

    def test_type_keeps_textboxes(self):
        filtered = _filter_snapshot(SAMPLE_SNAPSHOT, "type")
        assert "textbox" in filtered
        assert "button" not in filtered

    def test_verify_returns_full_snapshot(self):
        filtered = _filter_snapshot(SAMPLE_SNAPSHOT, "verify")
        assert filtered == SAMPLE_SNAPSHOT

    def test_empty_snapshot_returns_empty(self):
        assert _filter_snapshot("", "click") == ""

    def test_no_matching_roles_returns_empty(self):
        snapshot = "- heading \"Title\"\n- paragraph \"Some text\""
        filtered = _filter_snapshot(snapshot, "click")
        assert filtered.strip() == ""


# ===========================================================================
# 6. LLMGroundingResolver — parse_response
# ===========================================================================

class TestParseResponse:
    def test_valid_json_returns_target(self):
        text = json.dumps({
            "ref": 'role=button[name="Login"]',
            "confidence": 0.92,
            "reasoning": "Exact match",
        })
        targets = _parse_response(text, "llm_grounding")
        assert len(targets) == 1
        assert targets[0].ref == 'role=button[name="Login"]'
        assert targets[0].confidence == 0.92

    def test_low_confidence_returns_empty(self):
        text = json.dumps({"ref": "role=button", "confidence": 0.3, "reasoning": "weak"})
        assert _parse_response(text, "llm_grounding") == []

    def test_empty_ref_returns_empty(self):
        text = json.dumps({"ref": "", "confidence": 0.9, "reasoning": "no match"})
        assert _parse_response(text, "llm_grounding") == []

    def test_invalid_json_returns_empty(self):
        assert _parse_response("not json at all!!", "llm_grounding") == []

    def test_empty_string_returns_empty(self):
        assert _parse_response("", "llm_grounding") == []

    def test_markdown_fences_stripped(self):
        text = '```json\n{"ref": "role=button[name=\\"OK\\"]", "confidence": 0.88, "reasoning": "ok"}\n```'
        targets = _parse_response(text, "llm_grounding")
        assert len(targets) == 1
        assert targets[0].confidence == 0.88

    def test_signals_populated_in_metadata(self):
        text = json.dumps({"ref": 'role=button[name="Go"]', "confidence": 0.85, "reasoning": "good"})
        targets = _parse_response(text, "llm_grounding")
        signals = targets[0].metadata["signals"]
        assert "text_match" in signals
        assert "role_match" in signals
        assert signals["role_match"] == 1.0   # ref starts with role=

    def test_text_ref_gets_lower_role_match(self):
        text = json.dumps({"ref": "text=Login", "confidence": 0.75, "reasoning": "text"})
        targets = _parse_response(text, "llm_grounding")
        assert targets[0].metadata["signals"]["role_match"] == 0.5


# ===========================================================================
# 7. LLMGroundingResolver — full resolver with mock provider
# ===========================================================================

class TestLLMGroundingResolver:
    def _resolver(self, response_text: str) -> LLMGroundingResolver:
        return LLMGroundingResolver(provider=_mock_provider(response_text))

    def test_resolve_returns_target_on_success(self):
        response = json.dumps({
            "ref": 'role=button[name="Sign In"]',
            "confidence": 0.91,
            "reasoning": "Sign In matches Login intent",
        })
        resolver = self._resolver(response)
        intent = _make_intent(
            instruction="Click Login",
            action_type="click",
            context={"a11y_snapshot": SAMPLE_SNAPSHOT},
        )
        targets = resolver.resolve(intent)
        assert len(targets) == 1
        assert "Sign In" in targets[0].ref

    def test_resolve_returns_empty_without_snapshot(self):
        resolver = self._resolver('{"ref": "x", "confidence": 0.9, "reasoning": "?"}')
        intent = _make_intent(context={})
        targets = resolver.resolve(intent)
        assert targets == []

    def test_resolve_returns_empty_on_parse_failure(self):
        resolver = self._resolver("BROKEN JSON")
        intent = _make_intent(context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        targets = resolver.resolve(intent)
        assert targets == []

    def test_resolve_returns_empty_on_low_confidence(self):
        response = json.dumps({"ref": "role=button", "confidence": 0.2, "reasoning": "?"})
        resolver = self._resolver(response)
        intent = _make_intent(context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        targets = resolver.resolve(intent)
        assert targets == []

    def test_cost_level_is_high(self):
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        assert resolver.cost_level == "high"
        assert resolver.tier == 3

    def test_blocked_by_low_cost_policy(self):
        """max_cost_level=low must block LLMGroundingResolver (cost_level=high)."""
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        intent = _make_intent(
            context={"a11y_snapshot": SAMPLE_SNAPSHOT},
            max_cost_level="low",
        )
        assert resolver.can_run(intent) is False

    def test_allowed_by_high_cost_policy(self):
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        intent = _make_intent(
            context={"a11y_snapshot": SAMPLE_SNAPSHOT},
            max_cost_level="high",
        )
        assert resolver.can_run(intent) is True

    def test_required_context_is_a11y_snapshot(self):
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        assert "a11y_snapshot" in resolver.required_context()

    def test_resolver_name(self):
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        assert resolver.name == "llm_grounding"
        assert resolver.priority == 50

    def test_resolver_skipped_without_snapshot_in_can_run(self):
        """can_run returns False when a11y_snapshot missing from context."""
        resolver = LLMGroundingResolver(provider=_mock_provider("{}"))
        intent = _make_intent(context={})   # no a11y_snapshot
        assert resolver.can_run(intent) is False

    @pytest.mark.asyncio
    async def test_resolve_async_calls_provider(self):
        response = json.dumps({
            "ref": 'role=button[name="Sign In"]',
            "confidence": 0.88,
            "reasoning": "close match",
        })
        provider = _mock_provider(response)
        resolver = LLMGroundingResolver(provider=provider)
        intent = _make_intent(context={"a11y_snapshot": SAMPLE_SNAPSHOT})

        targets = await resolver.resolve_async(intent)
        assert len(targets) == 1
        provider.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_exception_returns_empty(self):
        provider = MagicMock(spec=ModelProvider)
        provider.provider_name = "mock"
        provider.model = "mock"
        provider.complete = AsyncMock(side_effect=RuntimeError("network error"))

        resolver = LLMGroundingResolver(provider=provider)
        intent = _make_intent(context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        targets = await resolver.resolve_async(intent)
        assert targets == []


# ===========================================================================
# 8. CandidateRanker — weighted signal formula
# ===========================================================================

class TestCandidateRankerSignals:
    def test_full_signals_weighted_correctly(self):
        """Verify formula: 0.3*tm + 0.2*rm + 0.15*v + 0.15*u + 0.1*p + 0.1*mh"""
        signals = {
            "text_match":     1.0,
            "role_match":     1.0,
            "visibility":     1.0,
            "uniqueness":     1.0,
            "proximity":      1.0,
            "memory_history": 1.0,
        }
        score = compute_confidence(signals)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_zero_signals_gives_zero(self):
        signals = {k: 0.0 for k in
                   ["text_match", "role_match", "visibility", "uniqueness", "proximity", "memory_history"]}
        assert compute_confidence(signals) == pytest.approx(0.0)

    def test_text_match_only(self):
        """text_match=1.0 alone contributes 0.30."""
        signals = {
            "text_match": 1.0, "role_match": 0.0, "visibility": 0.0,
            "uniqueness": 0.0, "proximity": 0.0, "memory_history": 0.0,
        }
        assert compute_confidence(signals) == pytest.approx(0.30, abs=0.001)

    def test_partial_signals_clamped(self):
        signals = {
            "text_match":     2.0,   # over 1.0 — should clamp
            "role_match":     1.0,
            "visibility":     1.0,
            "uniqueness":     1.0,
            "proximity":      1.0,
            "memory_history": 1.0,
        }
        score = compute_confidence(signals)
        assert score <= 1.0

    def test_ranker_uses_signals_when_present(self):
        """CandidateRanker.score() uses signals over raw confidence."""
        ranker = CandidateRanker()
        target = ResolvedTarget(
            ref="role=button",
            confidence=0.5,    # raw confidence — should be overridden
            resolver_name="test",
            metadata={
                "signals": {
                    "text_match":     1.0,
                    "role_match":     1.0,
                    "visibility":     1.0,
                    "uniqueness":     1.0,
                    "proximity":      1.0,
                    "memory_history": 1.0,
                }
            },
        )
        score = ranker.score(target)
        assert score == pytest.approx(1.0, abs=0.001)

    def test_ranker_passthrough_when_no_signals(self):
        """If no signals key, raw confidence is returned unchanged."""
        ranker = CandidateRanker()
        target = ResolvedTarget(
            ref="role=button",
            confidence=0.73,
            resolver_name="test",
            metadata={},
        )
        assert ranker.score(target) == pytest.approx(0.73)

    def test_ranker_rank_order(self):
        """Higher-signal target ranks above lower one."""
        ranker = CandidateRanker()
        high = ResolvedTarget(
            ref="role=button[name=\"Login\"]", confidence=0.9, resolver_name="test",
            metadata={"signals": {
                "text_match": 0.9, "role_match": 1.0, "visibility": 1.0,
                "uniqueness": 1.0, "proximity": 0.8, "memory_history": 0.0,
            }},
        )
        low = ResolvedTarget(
            ref="role=button[name=\"Cancel\"]", confidence=0.4, resolver_name="test",
            metadata={"signals": {
                "text_match": 0.1, "role_match": 1.0, "visibility": 1.0,
                "uniqueness": 0.5, "proximity": 0.2, "memory_history": 0.0,
            }},
        )
        ranked = ranker.rank([low, high])
        assert ranked[0].ref == high.ref

    def test_llm_grounding_signals_applied_by_ranker(self):
        """Signals from LLMGroundingResolver integrate correctly with ranker."""
        text = json.dumps({
            "ref": 'role=button[name="Submit"]',
            "confidence": 0.85,
            "reasoning": "best match",
        })
        targets = _parse_response(text, "llm_grounding")
        assert targets
        ranker = CandidateRanker()
        score = ranker.score(targets[0])
        # With confidence=0.85 as text_match, role_match=1.0, visibility=1.0,
        # uniqueness=0.7, proximity=0.5, memory_history=0.0:
        # 0.3*0.85 + 0.2*1.0 + 0.15*1.0 + 0.15*0.7 + 0.1*0.5 + 0.1*0.0
        # = 0.255 + 0.20 + 0.15 + 0.105 + 0.05 + 0.0 = 0.76
        assert score == pytest.approx(0.76, abs=0.01)


# ===========================================================================
# 9. Build prompt helper
# ===========================================================================

class TestBuildPrompt:
    def test_instruction_and_snapshot_in_prompt(self):
        prompt = _build_prompt("Click Login", "- button \"Sign In\"")
        assert "Click Login" in prompt
        assert "Sign In" in prompt

    def test_prompt_is_nonempty(self):
        prompt = _build_prompt("X", "Y")
        assert len(prompt) > 10
