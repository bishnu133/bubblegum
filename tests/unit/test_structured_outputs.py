"""
tests/unit/test_structured_outputs.py
======================================
Task #3 — guaranteed-schema structured output / tool-use.

Covers:
  * OpenAI provider sends response_format=json_schema (strict) when a schema is
    passed, and falls back to json_object when the model rejects it.
  * Anthropic provider forces a tool and serializes the tool input to .text.
  * The grounding + decompose schemas are shaped correctly and flow through.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from bubblegum.core.models.anthropic_provider import AnthropicProvider
from bubblegum.core.models.openai_provider import OpenAIProvider
from bubblegum.core.grounding.resolvers.llm_grounding import _GROUNDING_SCHEMA
from bubblegum.core.parser.llm_decompose import _DECOMPOSE_SCHEMA


# --------------------------------------------------------------------------- #
# Schema shape
# --------------------------------------------------------------------------- #

def test_grounding_schema_shape():
    s = _GROUNDING_SCHEMA["schema"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"ref", "confidence", "reasoning"}


def test_decompose_schema_shape():
    s = _DECOMPOSE_SCHEMA["schema"]
    assert s["additionalProperties"] is False
    assert "click" in s["properties"]["action_type"]["enum"]
    # nullable fields declared as ["string", "null"]
    assert s["properties"]["target_phrase"]["type"] == ["string", "null"]


# --------------------------------------------------------------------------- #
# OpenAI: json_schema strict mode + fallback
# --------------------------------------------------------------------------- #

class _OpenAIMessage:
    def __init__(self, content):
        self.content = content


class _OpenAIChoice:
    def __init__(self, content):
        self.message = _OpenAIMessage(content)


class _OpenAIUsage:
    prompt_tokens = 4
    completion_tokens = 2


class _OpenAIResp:
    def __init__(self, content):
        self.choices = [_OpenAIChoice(content)]
        self.usage = _OpenAIUsage()


class _RecordingCompletions:
    def __init__(self, sink, fail_first_on_schema=False):
        self._sink = sink
        self._fail_first = fail_first_on_schema
        self._calls = 0

    async def create(self, **kwargs):
        self._calls += 1
        self._sink.setdefault("calls", []).append(kwargs)
        if self._fail_first and self._calls == 1 and kwargs.get("response_format", {}).get("type") == "json_schema":
            raise RuntimeError("response_format json_schema is not supported by this model")
        return _OpenAIResp('{"ref": "text=Go", "confidence": 0.9, "reasoning": "ok"}')


class _FakeOpenAIClient:
    def __init__(self, sink, fail_first_on_schema=False):
        self.chat = type("_C", (), {})()
        self.chat.completions = _RecordingCompletions(sink, fail_first_on_schema)


def test_openai_uses_json_schema_strict():
    p = OpenAIProvider(model="gpt-4o-mini")
    sink: dict = {}
    p._client = _FakeOpenAIClient(sink)

    asyncio.run(p.complete("x", system="s", response_format="json", json_schema=_GROUNDING_SCHEMA))
    rf = sink["calls"][0]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "ground_element"


def test_openai_falls_back_to_json_object_when_schema_rejected():
    p = OpenAIProvider(model="old-model")
    sink: dict = {}
    p._client = _FakeOpenAIClient(sink, fail_first_on_schema=True)

    res = asyncio.run(p.complete("x", response_format="json", json_schema=_GROUNDING_SCHEMA))
    assert json.loads(res.text)["ref"] == "text=Go"
    # First call tried json_schema, retry used json_object.
    assert sink["calls"][0]["response_format"]["type"] == "json_schema"
    assert sink["calls"][1]["response_format"]["type"] == "json_object"


# --------------------------------------------------------------------------- #
# Anthropic: forced tool-use → tool input serialized into .text
# --------------------------------------------------------------------------- #

class _ToolBlock:
    type = "tool_use"

    def __init__(self, data):
        self.input = data


class _AnthMessages:
    def __init__(self, sink):
        self._sink = sink

    async def create(self, **kwargs):
        self._sink.update(kwargs)

        class _Usage:
            input_tokens = 5
            output_tokens = 3
            cache_read_input_tokens = 0

        class _Resp:
            usage = _Usage()
            content = [_ToolBlock({"ref": "role=button[name=\"Go\"]", "confidence": 0.88, "reasoning": "tool"})]

        return _Resp()


class _FakeAnthClient:
    def __init__(self, sink):
        self.messages = _AnthMessages(sink)


def test_anthropic_forces_tool_and_serializes_input(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "anthropic", type("m", (), {}))
    p = AnthropicProvider(model="claude-x", api_key="k")
    sink: dict = {}
    p._client = _FakeAnthClient(sink)

    res = asyncio.run(p.complete("x", system="SYS", response_format="json", json_schema=_GROUNDING_SCHEMA))
    # A single tool was defined and forced.
    assert sink["tools"][0]["name"] == "ground_element"
    assert sink["tool_choice"] == {"type": "tool", "name": "ground_element"}
    # The tool input round-trips as JSON text for the caller's parser.
    data = json.loads(res.text)
    assert data["confidence"] == 0.88
