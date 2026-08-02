"""M-C: Flutter / canvas auto-routing to vision.

Two layers:
  * the pure decision + candidate selection in ``core.mobile.canvas_routing``, and
  * the SDK wiring — ``_maybe_route_canvas`` (enables coordinate fallback on a
    canvas screen) and ``_maybe_resolve_canvas_vision`` (taps the best on-screen
    OCR match by coordinate when the hierarchy has nothing to pin).

All deterministic — no device, no OCR model. Vision candidates are supplied
directly, exactly as the RapidOCR backend would inject them.
"""

from __future__ import annotations

from bubblegum.core import sdk
from bubblegum.core.mobile.canvas_routing import (
    evaluate_canvas_routing,
    select_canvas_vision_candidate,
)
from bubblegum.core.schemas import ExecutionOptions, StepIntent
from bubblegum.core.vision.engine import VisionCandidate


# ----------------------------------------------------------------------
# evaluate_canvas_routing
# ----------------------------------------------------------------------

def test_flutter_framework_routes_to_vision():
    d = evaluate_canvas_routing(
        hierarchy_xml="<hierarchy><io.flutter.embedding.android.FlutterView/></hierarchy>",
        ui_framework={"framework": "flutter"},
        vision_available=True,
    )
    assert d["route_to_vision"] is True
    assert d["surface_type"] == "flutter"
    assert d["warnings"] == []


def test_canvas_surface_class_routes_to_vision():
    d = evaluate_canvas_routing(
        hierarchy_xml="<hierarchy><android.opengl.GLSurfaceView/></hierarchy>",
        ui_framework={"framework": "native_android"},
        vision_available=True,
    )
    assert d["route_to_vision"] is True
    assert d["surface_type"] == "canvas"


def test_hierarchy_with_no_text_routes_to_vision():
    d = evaluate_canvas_routing(
        hierarchy_xml="<hierarchy><node class='android.view.View'/><node class='android.view.View'/></hierarchy>",
        ui_framework={"framework": "native_android"},
        vision_available=True,
    )
    assert d["route_to_vision"] is True
    assert d["surface_type"] == "opaque"


def test_native_screen_with_text_stays_on_hierarchy():
    d = evaluate_canvas_routing(
        hierarchy_xml="<hierarchy><node text='Login'/><node text='Password'/></hierarchy>",
        ui_framework={"framework": "native_android"},
        vision_available=True,
    )
    assert d["route_to_vision"] is False
    assert d["surface_type"] == "native"


def test_absent_hierarchy_routes_to_vision():
    d = evaluate_canvas_routing(hierarchy_xml="", ui_framework=None, vision_available=True)
    assert d["route_to_vision"] is True
    assert d["surface_type"] == "unknown"


def test_routing_warns_when_vision_unavailable():
    d = evaluate_canvas_routing(
        hierarchy_xml="<hierarchy><io.flutter.FlutterView/></hierarchy>",
        ui_framework={"framework": "flutter"},
        vision_available=False,
    )
    assert d["route_to_vision"] is True
    assert "vision_backend_not_configured" in d["warnings"]


# ----------------------------------------------------------------------
# select_canvas_vision_candidate
# ----------------------------------------------------------------------

def _cands():
    return [
        VisionCandidate(label="Play", text="Play", bbox=[100, 200, 180, 240], confidence=0.95),
        VisionCandidate(label="Settings", text="Settings", bbox=[100, 300, 220, 340], confidence=0.9),
    ]


def test_select_candidate_exact_match():
    best = select_canvas_vision_candidate(
        target_phrase="Play", instruction="Tap Play", vision_candidates=_cands()
    )
    assert best is not None
    assert best["text"] == "Play"
    assert best["bbox"] == [100, 200, 180, 240]
    assert best["score"] == 1.0


def test_select_candidate_no_match_returns_none():
    best = select_canvas_vision_candidate(
        target_phrase="Checkout", instruction="Tap Checkout", vision_candidates=_cands()
    )
    assert best is None


def test_select_candidate_accepts_dict_candidates():
    cands = [{"text": "Continue", "bbox": [10, 20, 90, 60], "confidence": 0.8}]
    best = select_canvas_vision_candidate(
        target_phrase="Continue", instruction="Tap Continue", vision_candidates=cands
    )
    assert best is not None and best["text"] == "Continue"


# ----------------------------------------------------------------------
# SDK: _maybe_route_canvas
# ----------------------------------------------------------------------

def _intent(*, hierarchy: str, ui_framework: dict | None, action_type: str = "tap") -> StepIntent:
    intent = StepIntent(
        instruction="Tap Play",
        channel="mobile",
        platform="android",
        action_type=action_type,
        target_phrase="Play",
        options=ExecutionOptions(),
    )
    app_state = {"channel": "mobile"}
    if ui_framework is not None:
        app_state["ui_framework"] = ui_framework
    intent.context["app_state"] = app_state
    if hierarchy:
        intent.context["hierarchy_xml"] = hierarchy
    return intent


def test_route_canvas_enables_coordinate_fallback_on_flutter():
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"})
    decision = sdk._maybe_route_canvas(intent, "mobile")
    assert decision["route_to_vision"] is True
    assert intent.context["coordinate_click_fallback"] is True
    assert intent.context["canvas_routing"]["surface_type"] == "flutter"


def test_route_canvas_noop_on_native_screen():
    intent = _intent(hierarchy="<hierarchy><node text='Login'/></hierarchy>",
                     ui_framework={"framework": "native_android"})
    decision = sdk._maybe_route_canvas(intent, "mobile")
    assert decision["route_to_vision"] is False
    # Coordinate fallback is NOT force-enabled on an ordinary native screen.
    assert intent.context.get("coordinate_click_fallback") is not True


def test_route_canvas_noop_on_web():
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"})
    assert sdk._maybe_route_canvas(intent, "web") is None


def test_route_canvas_respects_config_disable(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "canvas_auto_route", False)
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"})
    assert sdk._maybe_route_canvas(intent, "mobile") is None


# ----------------------------------------------------------------------
# SDK: _maybe_resolve_canvas_vision
# ----------------------------------------------------------------------

def test_canvas_vision_taps_best_ocr_match():
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"})
    sdk._maybe_route_canvas(intent, "mobile")            # sets canvas_routing decision
    intent.context["vision_candidates"] = _cands()        # injected by RapidOCR path

    target = sdk._maybe_resolve_canvas_vision(intent, "mobile")

    assert target is not None
    assert target.resolver_name == "canvas_vision"
    assert target.point == [140, 220]                     # center of [100,200,180,240]
    assert target.ref == "point://140,220"
    assert target.metadata["matched_text"] == "Play"
    assert target.metadata["coordinate_click"] is True


def test_canvas_vision_skips_when_not_routed():
    intent = _intent(hierarchy="<hierarchy><node text='Login'/></hierarchy>",
                     ui_framework={"framework": "native_android"})
    sdk._maybe_route_canvas(intent, "mobile")             # native -> not routed
    intent.context["vision_candidates"] = _cands()
    assert sdk._maybe_resolve_canvas_vision(intent, "mobile") is None


def test_canvas_vision_skips_typing_action():
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"}, action_type="type")
    sdk._maybe_route_canvas(intent, "mobile")
    intent.context["vision_candidates"] = _cands()
    assert sdk._maybe_resolve_canvas_vision(intent, "mobile") is None


def test_canvas_vision_none_without_candidates():
    intent = _intent(hierarchy="<hierarchy><io.flutter.FlutterView/></hierarchy>",
                     ui_framework={"framework": "flutter"})
    sdk._maybe_route_canvas(intent, "mobile")
    assert sdk._maybe_resolve_canvas_vision(intent, "mobile") is None
