"""
AnthropicVisionProvider (PR3) — Claude vision backend for element grounding.

All tests inject a fake client, so no anthropic SDK or API key is required.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.core.vision import AnthropicVisionProvider, VisionCandidate


class _TextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text


class _Response:
    def __init__(self, text: str):
        self.content = [_TextBlock(text)]


class _FakeMessages:
    def __init__(self, response, recorder: dict):
        self._response = response
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.update(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeClient:
    def __init__(self, response, recorder: dict):
        self.messages = _FakeMessages(response, recorder)


def _client(response, recorder=None):
    return _FakeClient(response, recorder if recorder is not None else {})


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------

def test_requires_client_or_create_flag():
    with pytest.raises(ValueError, match="injected client or create_client"):
        AnthropicVisionProvider()


def test_rejects_empty_model():
    with pytest.raises(ValueError, match="model"):
        AnthropicVisionProvider(client=_client(_Response("{}")), model="  ")


def test_default_model_is_opus():
    p = AnthropicVisionProvider(client=_client(_Response("{}")))
    assert p._model == "claude-opus-4-8"


# ---------------------------------------------------------------------------
# detect_targets — happy path
# ---------------------------------------------------------------------------

def test_detect_targets_parses_candidates():
    payload = json.dumps({
        "candidates": [
            {"label": "Sign In", "role": "button", "text": "Sign In",
             "bbox": [10, 20, 110, 70], "confidence": 0.93},
        ]
    })
    provider = AnthropicVisionProvider(client=_client(_Response(payload)))
    out = provider.detect_targets(b"\x89PNG_fake", "click login")

    assert len(out) == 1
    c = out[0]
    assert isinstance(c, VisionCandidate)
    assert c.label == "Sign In"
    assert c.role == "button"
    assert c.bbox == [10, 20, 110, 70]
    assert c.confidence == 0.93


def test_detect_targets_sends_image_and_instruction():
    recorder: dict = {}
    provider = AnthropicVisionProvider(
        client=_client(_Response('{"candidates": []}'), recorder)
    )
    provider.detect_targets(b"\x89PNG_fake", "click the login button")

    content = recorder["messages"][0]["content"]
    image_block = next(b for b in content if b["type"] == "image")
    text_block = next(b for b in content if b["type"] == "text")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert "click the login button" in text_block["text"]
    assert recorder["model"] == "claude-opus-4-8"


def test_detect_targets_strips_code_fence():
    fenced = "```json\n" + json.dumps({"candidates": [
        {"label": "OK", "confidence": 0.8}
    ]}) + "\n```"
    provider = AnthropicVisionProvider(client=_client(_Response(fenced)))
    out = provider.detect_targets(b"img", "confirm")
    assert len(out) == 1
    assert out[0].label == "OK"


# ---------------------------------------------------------------------------
# Fail-safe behaviour
# ---------------------------------------------------------------------------

def test_empty_image_returns_empty_with_diagnostic():
    provider = AnthropicVisionProvider(client=_client(_Response("{}")))
    assert provider.detect_targets(b"", "x") == []
    assert provider.get_last_diagnostic()["code"] == "empty_image"


def test_request_failure_is_fail_safe():
    provider = AnthropicVisionProvider(client=_client(RuntimeError("boom")))
    assert provider.detect_targets(b"img", "x") == []
    diag = provider.get_last_diagnostic()
    assert diag["code"] == "request_failed"
    assert diag["provider"] == "anthropic_vision"


def test_unparseable_response_is_fail_safe():
    provider = AnthropicVisionProvider(client=_client(_Response("not json")))
    assert provider.detect_targets(b"img", "x") == []
    assert provider.get_last_diagnostic()["code"] == "parse_failed"


def test_missing_api_key_does_not_leak():
    # A diagnostic must never carry the raw exception message / secrets.
    provider = AnthropicVisionProvider(client=_client(RuntimeError("key sk-secret")))
    provider.detect_targets(b"img", "x")
    diag = provider.get_last_diagnostic()
    assert "sk-secret" not in json.dumps(diag)
