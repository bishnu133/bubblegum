"""Unit tests for the mobile gesture vocabulary (M1).

Browser/device-free: parser recognition of gesture verbs (long press / double
tap / pinch / zoom / drag) and the AppiumAdapter dispatch into the right
``mobile:`` gesture command on Android and iOS, captured via a fake driver.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.parser.instruction import decompose, infer_action_type, match_gesture
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction,action,target",
    [
        ("Long press the message", "long_press", "message"),
        ("long-press Photo", "long_press", "Photo"),
        ("Press and hold the Album", "long_press", "Album"),
        ("Hold the thumbnail", "long_press", "thumbnail"),
        ("Double tap the image", "double_tap", "image"),
        ("double-tap Like", "double_tap", "Like"),
        ("Pinch the map", "pinch", "map"),
        ("Zoom out the map", "pinch", "map"),
        ("Zoom in on the photo", "zoom", "photo"),
        ("Spread the picture", "zoom", "picture"),
        ("Drag the slider", "drag", "slider"),
    ],
)
def test_match_gesture_recognizes_verbs(instruction, action, target):
    result = match_gesture(instruction)
    assert result is not None
    assert (result[0], result[1]) == (action, target)


def test_drag_extracts_direction_into_value():
    assert match_gesture("Drag the slider to the right") == ("drag", "slider", "right")
    assert match_gesture("Drag the handle up") == ("drag", "handle", "up")
    assert match_gesture("Drag the card") == ("drag", "card", None)


def test_non_gesture_and_named_elements_are_not_hijacked():
    # A button literally named "Long press" is still a click.
    assert match_gesture("Click the Long press button") is None
    # Bare "press" / "double click" are not mobile gestures.
    assert match_gesture("Press Login") is None
    assert match_gesture("Double click Submit") is None
    # Verify phrasing is untouched.
    assert match_gesture("Verify the long press menu is visible") is None


def test_decompose_returns_gesture_action_and_target():
    parsed = decompose("Long press the message")
    assert parsed.action_type == "long_press"
    assert parsed.target_phrase == "message"
    assert parsed.confident is True

    drag = decompose("Drag the slider right")
    assert drag.action_type == "drag"
    assert drag.target_phrase == "slider"
    assert drag.input_value == "right"


def test_decompose_respects_explicit_action_type_override():
    parsed = decompose("Long press the message", {"action_type": "tap"})
    assert parsed.action_type == "tap"


def test_infer_action_type_detects_gestures():
    assert infer_action_type("Long press the message", {}) == "long_press"
    assert infer_action_type("Double tap the image", {}) == "double_tap"
    assert infer_action_type("Click Login", {}) == "click"


# ---------------------------------------------------------------------------
# AppiumAdapter gesture dispatch
# ---------------------------------------------------------------------------


class _FakeElement:
    id = "elem-1"
    location = {"x": 100, "y": 200}
    size = {"width": 80, "height": 40}


class _FakeDriver:
    def __init__(self, platform="Android"):
        self.capabilities = {"platformName": platform}
        self.scripts: list[tuple[str, dict]] = []

    def execute_script(self, name, args=None):
        self.scripts.append((name, args or {}))
        return None


def _run_gesture(driver, action_type, *, input_value=None):
    adapter = AppiumAdapter(driver)
    plan = ActionPlan(
        action_type=action_type, target_hint="x", input_value=input_value,
        options=ExecutionOptions(),
    )
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")
    # Resolve to our fake element directly; we only care about the gesture call.
    adapter._find_element = lambda ref: _FakeElement()  # type: ignore[method-assign]
    result = asyncio.run(adapter.execute(plan, target))
    assert result.success is True
    return driver.scripts


@pytest.mark.parametrize(
    "action,expected_script",
    [
        ("long_press", "mobile: longClickGesture"),
        ("double_tap", "mobile: doubleClickGesture"),
        ("pinch", "mobile: pinchCloseGesture"),
        ("zoom", "mobile: pinchOpenGesture"),
        ("drag", "mobile: dragGesture"),
    ],
)
def test_android_gesture_dispatch(action, expected_script):
    scripts = _run_gesture(_FakeDriver("Android"), action)
    assert scripts[-1][0] == expected_script
    assert scripts[-1][1].get("elementId") == "elem-1"


@pytest.mark.parametrize(
    "action,expected_script",
    [
        ("long_press", "mobile: touchAndHold"),
        ("double_tap", "mobile: doubleTap"),
        ("pinch", "mobile: pinch"),
        ("zoom", "mobile: pinch"),
        ("drag", "mobile: dragFromToForDuration"),
    ],
)
def test_ios_gesture_dispatch(action, expected_script):
    scripts = _run_gesture(_FakeDriver("iOS"), action)
    assert scripts[-1][0] == expected_script


def test_long_press_duration_override():
    scripts = _run_gesture(_FakeDriver("Android"), "long_press", input_value="2500")
    assert scripts[-1][1]["duration"] == 2500


def test_long_press_default_duration():
    scripts = _run_gesture(_FakeDriver("Android"), "long_press")
    assert scripts[-1][1]["duration"] == 1000


def test_ios_pinch_scale_direction():
    zoom_out = _run_gesture(_FakeDriver("iOS"), "pinch")
    zoom_in = _run_gesture(_FakeDriver("iOS"), "zoom")
    assert zoom_out[-1][1]["scale"] < 1.0   # pinch closes / zooms out
    assert zoom_in[-1][1]["scale"] > 1.0    # spread opens / zooms in


def test_drag_direction_offsets_endpoint():
    scripts = _run_gesture(_FakeDriver("Android"), "drag", input_value="right")
    # element centre is (140, 220); right drag adds +300 to x.
    assert scripts[-1][1]["endX"] == 440
    assert scripts[-1][1]["endY"] == 220
