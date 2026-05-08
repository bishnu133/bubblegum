from __future__ import annotations

from bubblegum.core.vision.backends.openai import OpenAIVisionProvider


class _FakeResponse:
    def __init__(self, text: str):
        self.output_text = text


class _FakeClient:
    def __init__(self, response=None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.responses = self

    def create(self, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


def test_last_diagnostic_cleared_on_successful_parse():
    client = _FakeClient(_FakeResponse('{"candidates": [{"label": "Login", "confidence": 0.9}]}'))
    provider = OpenAIVisionProvider(client=client)

    out = provider.detect_targets(b"img", "Click Login")

    assert len(out) == 1
    assert provider.last_diagnostic is None
    assert provider.get_last_diagnostic() is None


def test_empty_image_sets_input_diagnostic():
    client = _FakeClient(_FakeResponse('{"candidates": []}'))
    provider = OpenAIVisionProvider(client=client)

    out = provider.detect_targets(b"", "Click Login")

    assert out == []
    diag = provider.get_last_diagnostic()
    assert isinstance(diag, dict)
    assert diag == {
        "provider": "openai_vision",
        "code": "empty_image",
        "stage": "input",
        "recoverable": True,
        "message": "Screenshot bytes were empty; vision request skipped.",
    }


def test_client_init_failure_sets_sanitized_diagnostic(monkeypatch):
    provider = OpenAIVisionProvider(client=_FakeClient(_FakeResponse('{"candidates": []}')))
    provider._client = None

    def _raise_client_init():
        raise ImportError("OPENAI_API_KEY=super-secret")

    monkeypatch.setattr(provider, "_ensure_client", _raise_client_init)

    out = provider.detect_targets(b"img", "Click Login")

    assert out == []
    diag = provider.get_last_diagnostic()
    assert isinstance(diag, dict)
    assert diag["provider"] == "openai_vision"
    assert diag["code"] == "client_init_failed"
    assert diag["stage"] == "client_init"
    assert diag["recoverable"] is True
    assert diag["message"]
    assert diag["exception_type"] == "ImportError"
    assert "super-secret" not in str(diag)
    assert "OPENAI_API_KEY" not in str(diag)


def test_request_exception_sets_request_failed_diagnostic():
    client = _FakeClient(exc=RuntimeError("api_key=top-secret-and-sensitive"))
    provider = OpenAIVisionProvider(client=client)

    out = provider.detect_targets(b"raw-bytes:secret", "Click Login")

    assert out == []
    diag = provider.get_last_diagnostic()
    assert isinstance(diag, dict)
    assert diag["code"] == "request_failed"
    assert diag["stage"] == "request"
    assert diag["provider"] == "openai_vision"
    assert diag["recoverable"] is True
    assert diag["exception_type"] == "RuntimeError"
    text = str(diag)
    assert "top-secret-and-sensitive" not in text
    assert "raw-bytes:secret" not in text


def test_malformed_json_sets_parse_failed_diagnostic():
    client = _FakeClient(_FakeResponse("{not-json"))
    provider = OpenAIVisionProvider(client=client)

    out = provider.detect_targets(b"img", "Click Login")

    assert out == []
    diag = provider.get_last_diagnostic()
    assert isinstance(diag, dict)
    assert diag["code"] == "parse_failed"
    assert diag["stage"] == "parse"
    assert diag["provider"] == "openai_vision"
    assert diag["recoverable"] is True
    assert diag["exception_type"] == "JSONDecodeError"


def test_invalid_response_sets_sanitized_diagnostic_without_payload_leak():
    client = _FakeClient(_FakeResponse("  "))
    provider = OpenAIVisionProvider(client=client)

    out = provider.detect_targets(b"binary\x00\x01", "Click Login")

    assert out == []
    diag = provider.get_last_diagnostic()
    assert isinstance(diag, dict)
    assert diag["code"] == "invalid_response"
    assert diag["stage"] == "parse"
    assert diag["provider"] == "openai_vision"
    assert diag["recoverable"] is True
    assert set(diag.keys()).issubset({"provider", "code", "stage", "recoverable", "message", "exception_type"})
    text = str(diag)
    assert "binary" not in text
    assert "base64" not in text
    assert "data:image/png;base64" not in text
