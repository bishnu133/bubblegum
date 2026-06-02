"""Unit tests for AnthropicProvider — all mocked, no real API calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bubblegum.core.models.anthropic_provider import AnthropicProvider, _strip_code_fence


# ---------------------------------------------------------------------------
# _strip_code_fence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', '{"a": 1}'),
    ('```json\n{"a": 1}\n```', '{"a": 1}'),
    ('```\n{"a": 1}\n```', '{"a": 1}'),
    ('  ```json\n{"a": 1}\n```  ', '{"a": 1}'),
])
def test_strip_code_fence(raw, expected):
    assert _strip_code_fence(raw) == expected


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

def test_raises_on_empty_model():
    with pytest.raises(ValueError, match="model"):
        AnthropicProvider(model="")


def test_raises_provider_config_error_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    import asyncio
    with pytest.raises(Exception, match="ANTHROPIC_API_KEY"):
        asyncio.run(provider.complete("hello"))


def test_raises_provider_config_error_when_anthropic_not_installed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    import sys
    import asyncio
    original = sys.modules.get("anthropic")
    sys.modules["anthropic"] = None  # type: ignore
    try:
        with pytest.raises(Exception, match="anthropic.*not installed"):
            asyncio.run(provider.complete("hello"))
    finally:
        if original is not None:
            sys.modules["anthropic"] = original
        else:
            del sys.modules["anthropic"]


# ---------------------------------------------------------------------------
# complete() — mocked anthropic SDK
# ---------------------------------------------------------------------------

def _make_mock_response(text: str, input_tokens: int = 10, output_tokens: int = 5):
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


@pytest.mark.asyncio
async def test_complete_returns_completion_result(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    mock_response = _make_mock_response("Hello world")
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await provider.complete("Say hello")

    assert result.text == "Hello world"
    assert result.provider == "anthropic"
    assert result.model == "claude-haiku-4-5-20251001"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_complete_json_format_strips_fence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    mock_response = _make_mock_response('```json\n{"key": "value"}\n```')
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await provider.complete("Return JSON", response_format="json")

    assert result.text == '{"key": "value"}'


@pytest.mark.asyncio
async def test_complete_json_format_appends_instruction_to_system(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    captured_kwargs: dict = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return _make_mock_response('{"ok": true}')

    mock_client = MagicMock()
    mock_client.messages.create = fake_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await provider.complete("Return JSON", system="Be helpful.", response_format="json")

    assert "system" in captured_kwargs
    assert "JSON" in captured_kwargs["system"]
    assert "Be helpful." in captured_kwargs["system"]


@pytest.mark.asyncio
async def test_complete_no_system_omits_key_when_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")

    captured_kwargs: dict = {}

    async def fake_create(**kwargs):
        captured_kwargs.update(kwargs)
        return _make_mock_response("hi")

    mock_client = MagicMock()
    mock_client.messages.create = fake_create

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await provider.complete("hi")

    assert "system" not in captured_kwargs
