from __future__ import annotations

import base64

from bubblegum.core.vision.backends import OpenAIVisionProvider
from bubblegum.core.vision.engine import VisionCandidate


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponsesAPI:
    def __init__(self, *, output_text: str = '{"candidates": []}', raise_exc: Exception | None = None) -> None:
        self.output_text = output_text
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.output_text)


class _FakeClient:
    def __init__(self, responses_api: _FakeResponsesAPI) -> None:
        self.responses = responses_api


def test_provider_constructs_with_injected_client_and_export_available() -> None:
    provider = OpenAIVisionProvider(client=_FakeClient(_FakeResponsesAPI()))
    assert isinstance(provider, OpenAIVisionProvider)


def test_detect_targets_sends_base64_image_and_instruction_and_parses_candidates() -> None:
    api = _FakeResponsesAPI(
        output_text=(
            '{"candidates": ['
            '{"label":" Login ","bbox":[1.2,2,3,4],"confidence":1.4,"role":" button ","text":" Sign in "},'
            '{"label":"Help","bbox":null,"confidence":0.5}'
            ']}'
        )
    )
    provider = OpenAIVisionProvider(client=_FakeClient(api), model="gpt-test")

    raw = b"fake-png-bytes"
    out = provider.detect_targets(raw, "Click Login", context={"source": "unit"})

    assert len(out) == 2
    assert isinstance(out[0], VisionCandidate)
    assert out[0].label == "Login"
    assert out[0].bbox == [1, 2, 3, 4]
    assert out[0].confidence == 1.0
    assert out[0].role == "button"
    assert out[0].text == "Sign in"

    call = api.calls[0]
    assert call["model"] == "gpt-test"
    assert call["response_format"] == {"type": "json_object"}
    content = call["input"][0]["content"]
    text_prompt = content[0]["text"]
    image_payload = content[1]["image_url"]

    assert "Instruction: Click Login" in text_prompt
    assert "Context:" in text_prompt
    assert image_payload.startswith("data:image/png;base64,")
    encoded = image_payload.split(",", 1)[1]
    assert encoded == base64.b64encode(raw).decode("ascii")
    assert raw.decode("latin1") not in text_prompt


def test_malformed_json_returns_empty() -> None:
    provider = OpenAIVisionProvider(client=_FakeClient(_FakeResponsesAPI(output_text="{not-json")))
    assert provider.detect_targets(b"img", "Click") == []


def test_provider_exception_returns_empty() -> None:
    provider = OpenAIVisionProvider(client=_FakeClient(_FakeResponsesAPI(raise_exc=RuntimeError("boom"))))
    assert provider.detect_targets(b"img", "Click") == []


def test_empty_image_bytes_returns_empty_without_calling_client() -> None:
    api = _FakeResponsesAPI()
    provider = OpenAIVisionProvider(client=_FakeClient(api))
    assert provider.detect_targets(b"", "Click") == []
    assert api.calls == []


def test_missing_client_configuration_raises_clear_error() -> None:
    try:
        OpenAIVisionProvider()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "injected client" in str(exc)
