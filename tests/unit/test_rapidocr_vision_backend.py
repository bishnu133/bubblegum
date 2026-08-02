"""M-B: offline, on-device OCR grounding via RapidOCR.

Covers the pure conversion (RapidOCR result -> VisionCandidate), the provider's
fail-safe behaviour when the engine is absent, factory selection, and the config
/ SDK gates that make ``vision_backend="rapidocr"`` local by construction — so it
works with ``enable_vision`` alone and needs no hosted-vision privacy opt-in.

No RapidOCR model is downloaded: the engine is injected as a small fake, exactly
as the hosted backends inject a fake client.
"""

from __future__ import annotations

from bubblegum.core.config import LOCAL_VISION_BACKENDS, BubblegumConfig
from bubblegum.core.vision.backends.rapidocr import (
    RapidOCRVisionProvider,
    candidates_from_rapidocr_result,
)
from bubblegum.core.vision.engine import VisionCandidate
from bubblegum.core.vision.factory import get_vision_provider
from bubblegum.core import sdk
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# A RapidOCR-style result: [polygon, text, score] per detected line.
_RESULT = [
    [[[10, 20], [110, 20], [110, 60], [10, 60]], "Login", 0.95],
    [[[10, 80], [210, 80], [210, 120], [10, 120]], "Forgot password", 0.88],
    [[[0, 0], [5, 0], [5, 5], [0, 5]], "x", 0.10],  # below default min_confidence
]


def _fake_engine_tuple(_img):
    return (_RESULT, 12.3)  # RapidOCR returns (result, elapse)


def _fake_engine_bare(_img):
    return _RESULT


# ----------------------------------------------------------------------
# Pure conversion
# ----------------------------------------------------------------------

def test_conversion_polygon_to_bbox_and_confidence_filter():
    cands = candidates_from_rapidocr_result(_RESULT, min_confidence=0.3, max_candidates=200)
    assert [c.text for c in cands] == ["Login", "Forgot password"]  # 0.10 dropped
    login = cands[0]
    assert login.label == "Login"
    assert login.bbox == [10, 20, 110, 60]        # polygon reduced to axis-aligned bbox
    assert login.confidence == 0.95


def test_conversion_accepts_axis_aligned_box_form():
    result = [[[10, 20, 110, 60], "A", 0.9]]
    cands = candidates_from_rapidocr_result(result, min_confidence=0.0, max_candidates=10)
    assert cands[0].bbox == [10, 20, 110, 60]


def test_conversion_respects_max_candidates_cap():
    cands = candidates_from_rapidocr_result(_RESULT, min_confidence=0.0, max_candidates=1)
    assert len(cands) == 1


def test_conversion_skips_malformed_items():
    result = [
        "not-a-line",
        [[[0, 0]], "", 0.9],                       # empty text
        [None, "text-without-box", 0.9],           # bad box
        [[[1, 1], [2, 2], [3, 3], [4, 4]], "ok", 0.9],
    ]
    cands = candidates_from_rapidocr_result(result, min_confidence=0.0, max_candidates=10)
    assert [c.text for c in cands] == ["ok"]


# ----------------------------------------------------------------------
# Provider (injected fake engine — no model download)
# ----------------------------------------------------------------------

def test_provider_detect_targets_with_tuple_engine():
    provider = RapidOCRVisionProvider(engine=_fake_engine_tuple)
    cands = provider.detect_targets(b"pngbytes", "Tap Login")
    assert isinstance(cands[0], VisionCandidate)
    assert [c.text for c in cands] == ["Login", "Forgot password"]


def test_provider_detect_targets_with_bare_result_engine():
    provider = RapidOCRVisionProvider(engine=_fake_engine_bare)
    cands = provider.detect_targets(b"pngbytes", "Tap Login")
    assert [c.text for c in cands] == ["Login", "Forgot password"]


def test_provider_empty_image_returns_empty():
    provider = RapidOCRVisionProvider(engine=_fake_engine_tuple)
    assert provider.detect_targets(b"", "Tap Login") == []


def test_provider_is_failsafe_when_engine_unavailable():
    # No injected engine and creation disabled -> dormant, never raises.
    provider = RapidOCRVisionProvider(engine=None, create_engine=False)
    assert provider.detect_targets(b"pngbytes", "Tap Login") == []


def test_provider_swallows_engine_errors():
    def _boom(_img):
        raise RuntimeError("bad frame")

    provider = RapidOCRVisionProvider(engine=_boom)
    assert provider.detect_targets(b"pngbytes", "Tap Login") == []


# ----------------------------------------------------------------------
# Factory + config gates (rapidocr is local by construction)
# ----------------------------------------------------------------------

def test_factory_builds_rapidocr_provider():
    cfg = BubblegumConfig()
    cfg.grounding.vision_backend = "rapidocr"
    provider = get_vision_provider(cfg)
    assert isinstance(provider, RapidOCRVisionProvider)
    assert provider.provider_name == "rapidocr"


def test_rapidocr_is_in_local_backends():
    assert "rapidocr" in LOCAL_VISION_BACKENDS


def test_vision_enabled_true_for_local_backend_without_privacy_flags():
    cfg = BubblegumConfig()
    cfg.grounding.enable_vision = True
    cfg.grounding.vision_backend = "rapidocr"
    # All privacy flags remain at their (False) defaults.
    assert cfg.privacy.send_screenshots is False
    assert cfg.privacy.vision_is_local is False
    assert cfg.vision_enabled is True


def test_vision_enabled_false_when_vision_disabled():
    cfg = BubblegumConfig()
    cfg.grounding.enable_vision = False
    cfg.grounding.vision_backend = "rapidocr"
    assert cfg.vision_enabled is False


def test_sdk_gates_treat_rapidocr_as_local(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "vision_backend", "rapidocr")
    monkeypatch.setattr(sdk._config.grounding, "enable_vision", True)
    # Master privacy opt-in stays off — a local backend must not need it.
    monkeypatch.setattr(sdk._config.privacy, "process_screenshots_for_vision", False)

    assert sdk._vision_backend_is_local() is True
    assert sdk._vision_privacy_ok() is True

    intent = StepIntent(
        instruction="Tap Login",
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase="Login",
        options=ExecutionOptions(max_cost_level="low"),
    )
    # Local vision is effectively free, so a low-cost policy still allows it.
    assert sdk._allows_provider_vision_cost(intent) is True


def test_sdk_gates_hosted_backend_still_requires_optin(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "vision_backend", "openai")
    monkeypatch.setattr(sdk._config.privacy, "process_screenshots_for_vision", False)
    assert sdk._vision_backend_is_local() is False
    assert sdk._vision_privacy_ok() is False
