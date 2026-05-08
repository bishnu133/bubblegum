from __future__ import annotations

from bubblegum.core.vision.backends import CallableVisionProvider
from bubblegum.core.vision.engine import VisionCandidate, build_vision_candidates_from_screenshot


def test_callable_backend_returns_candidates_and_pipeline_normalizes() -> None:
    provider = CallableVisionProvider(
        lambda image_bytes, instruction, context: [
            {
                "label": f" {instruction} ",
                "bbox": [1.2, 2, 30, 40],
                "confidence": 1.3,
                "role": " button ",
                "text": " Sign in ",
            },
            VisionCandidate(label="Submit", bbox=(5, 6, 7, 8), confidence=-0.5, role="cta", text="Go"),
        ]
    )

    out = build_vision_candidates_from_screenshot(
        b"png-bytes",
        instruction="Click Login",
        provider=provider,
        enabled=True,
        privacy_gate=True,
    )

    assert len(out) == 2
    assert out[0].label == "Click Login"
    assert out[0].bbox == [1, 2, 30, 40]
    assert out[0].confidence == 1.0
    assert out[0].role == "button"
    assert out[0].text == "Sign in"
    assert out[1].label == "Submit"
    assert out[1].bbox == [5, 6, 7, 8]
    assert out[1].confidence == 0.0


def test_callable_backend_malformed_output_is_dropped() -> None:
    provider = CallableVisionProvider(
        lambda image_bytes, instruction, context: [
            {},
            {"label": "   "},
            {"label": "ok", "bbox": [1, 2, 3]},
            {"label": "ok", "bbox": [1, "x", 3, 4]},
            {"label": "ok", "confidence": "bad"},
        ]
    )

    out = build_vision_candidates_from_screenshot(
        b"png-bytes",
        instruction="Click Login",
        provider=provider,
        enabled=True,
        privacy_gate=True,
    )

    assert len(out) == 1
    assert out[0].label == "ok"
    assert out[0].confidence == 0.0


def test_callable_exception_returns_empty_via_pipeline() -> None:
    def _boom(image_bytes, instruction, context):
        raise RuntimeError("boom")

    provider = CallableVisionProvider(_boom)

    out = build_vision_candidates_from_screenshot(
        b"png-bytes",
        instruction="Click Login",
        provider=provider,
        enabled=True,
        privacy_gate=True,
    )

    assert out == []


def test_callable_not_invoked_when_disabled_or_gated_or_screenshot_missing() -> None:
    calls = {"count": 0}

    def _fn(image_bytes, instruction, context):
        calls["count"] += 1
        return [{"label": "Login", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    provider = CallableVisionProvider(_fn)

    assert build_vision_candidates_from_screenshot(
        b"png-bytes", instruction="x", provider=provider, enabled=False, privacy_gate=True
    ) == []
    assert build_vision_candidates_from_screenshot(
        b"png-bytes", instruction="x", provider=provider, enabled=True, privacy_gate=False
    ) == []
    assert build_vision_candidates_from_screenshot(
        None, instruction="x", provider=provider, enabled=True, privacy_gate=True
    ) == []
    assert calls["count"] == 0


def test_callable_receives_image_instruction_and_context() -> None:
    seen: dict[str, object] = {}

    def _fn(image_bytes, instruction, context):
        seen["image_bytes"] = image_bytes
        seen["instruction"] = instruction
        seen["context"] = context
        return [{"label": "Login", "bbox": [1, 2, 3, 4], "confidence": 0.9}]

    provider = CallableVisionProvider(_fn)
    ctx = {"source": "test"}

    out = build_vision_candidates_from_screenshot(
        b"img-123",
        instruction="Click Login",
        provider=provider,
        enabled=True,
        privacy_gate=True,
        context=ctx,
    )

    assert len(out) == 1
    assert seen["image_bytes"] == b"img-123"
    assert seen["instruction"] == "Click Login"
    assert seen["context"] == ctx
