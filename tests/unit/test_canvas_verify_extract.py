"""M-C2: OCR-based verify/extract on canvas/Flutter screens.

On a self-drawn screen the accessibility hierarchy has no text, so a
``text_visible`` assertion and a text extraction must read the pixels. These
tests drive the pure ``ocr_text_present`` helper and the two SDK hooks
(``_maybe_verify_canvas_text`` / ``_maybe_extract_canvas_text``) with injected
OCR candidates — no device, no OCR model.
"""

from __future__ import annotations

import time

from bubblegum.core import sdk
from bubblegum.core.mobile.canvas_routing import ocr_text_present
from bubblegum.core.schemas import ExecutionOptions, StepIntent
from bubblegum.core.vision.engine import VisionCandidate


# ----------------------------------------------------------------------
# ocr_text_present
# ----------------------------------------------------------------------

def _cands():
    return [
        VisionCandidate(label="Level", text="Level", bbox=[10, 10, 60, 40], confidence=0.95),
        VisionCandidate(label="2", text="2", bbox=[62, 10, 80, 40], confidence=0.9),
        VisionCandidate(label="Play", text="Play", bbox=[10, 80, 90, 120], confidence=0.93),
    ]


def test_ocr_text_present_exact_single_box():
    r = ocr_text_present("Play", _cands())
    assert r["found"] is True
    assert r["matched_text"] == "Play"


def test_ocr_text_present_substring():
    cands = [VisionCandidate(label="Welcome back", text="Welcome back", bbox=[0, 0, 100, 20], confidence=0.9)]
    assert ocr_text_present("Welcome", cands)["found"] is True


def test_ocr_text_present_spanning_multiple_boxes():
    # "Level 2" is split across two OCR boxes; the joined-screen fallback matches.
    assert ocr_text_present("Level 2", _cands())["found"] is True


def test_ocr_text_present_not_found():
    assert ocr_text_present("Checkout", _cands())["found"] is False


def test_ocr_text_present_empty_inputs():
    assert ocr_text_present("", _cands())["found"] is False
    assert ocr_text_present("Play", [])["found"] is False


# ----------------------------------------------------------------------
# _maybe_verify_canvas_text
# ----------------------------------------------------------------------

_ROUTED = {"route_to_vision": True, "surface_type": "flutter", "reason": "flutter_detected"}


def _verify_intent(instruction: str) -> StepIntent:
    intent = StepIntent(
        instruction=instruction,
        channel="mobile",
        platform="android",
        action_type="verify",
        options=ExecutionOptions(),
    )
    intent.context["canvas_routing"] = dict(_ROUTED)
    intent.context["vision_candidates"] = _cands()
    return intent


def test_verify_canvas_passes_when_text_visible():
    intent = _verify_intent('the screen shows "Play"')
    res = sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, {}, time.monotonic())
    assert res is not None
    assert res.status == "passed"
    assert res.target.metadata["source"] == "canvas_ocr"


def test_verify_canvas_fails_when_text_missing():
    intent = _verify_intent('the screen shows "Checkout"')
    res = sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, {}, time.monotonic())
    assert res is not None
    assert res.status == "failed"


def test_verify_canvas_multiple_quoted_all_required():
    intent = _verify_intent('the screen shows "Play" and "Checkout"')
    res = sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, {}, time.monotonic())
    assert res.status == "failed"  # Play visible, Checkout not -> overall fail


def test_verify_canvas_no_candidates_gives_actionable_error():
    intent = _verify_intent('the screen shows "Play"')
    intent.context["vision_candidates"] = []
    res = sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, {}, time.monotonic())
    assert res.status == "failed"
    assert "vision_backend" in res.error.message


def test_verify_canvas_skips_when_not_routed():
    intent = _verify_intent('the screen shows "Play"')
    intent.context["canvas_routing"] = {"route_to_vision": False}
    assert sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, {}, time.monotonic()) is None


def test_verify_canvas_skips_on_web():
    intent = _verify_intent('the screen shows "Play"')
    assert sdk._maybe_verify_canvas_text(intent, "web", intent.instruction, {}, time.monotonic()) is None


def test_verify_canvas_skips_non_text_visible_assertion():
    intent = _verify_intent('the activity is "MainActivity"')
    kwargs = {"assertion_type": "activity"}
    assert sdk._maybe_verify_canvas_text(intent, "mobile", intent.instruction, kwargs, time.monotonic()) is None


# ----------------------------------------------------------------------
# _maybe_extract_canvas_text
# ----------------------------------------------------------------------

def _extract_intent(target_phrase: str) -> StepIntent:
    intent = StepIntent(
        instruction=f"Get {target_phrase}",
        channel="mobile",
        platform="android",
        action_type="extract",
        target_phrase=target_phrase,
        options=ExecutionOptions(),
    )
    intent.context["canvas_routing"] = dict(_ROUTED)
    intent.context["vision_candidates"] = _cands()
    return intent


def test_extract_canvas_returns_matched_text():
    intent = _extract_intent("Play")
    res = sdk._maybe_extract_canvas_text(intent, "mobile", intent.instruction, time.monotonic())
    assert res is not None
    assert res.status == "passed"
    assert res.target.metadata["extracted_value"] == "Play"


def test_extract_canvas_skips_when_not_routed():
    intent = _extract_intent("Play")
    intent.context["canvas_routing"] = {"route_to_vision": False}
    assert sdk._maybe_extract_canvas_text(intent, "mobile", intent.instruction, time.monotonic()) is None


def test_extract_canvas_none_without_candidates():
    intent = _extract_intent("Play")
    intent.context["vision_candidates"] = []
    assert sdk._maybe_extract_canvas_text(intent, "mobile", intent.instruction, time.monotonic()) is None


def test_extract_canvas_none_on_no_match():
    intent = _extract_intent("Checkout")
    assert sdk._maybe_extract_canvas_text(intent, "mobile", intent.instruction, time.monotonic()) is None
