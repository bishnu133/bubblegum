"""Unit tests for mobile system / hardware actions (M2).

Browser/device-free: parser recognition of system verbs, AppiumAdapter dispatch
to the right driver call per platform (captured via a fake driver), and the
sdk.act routing that sends mobile system verbs to the system path before
grounding (plus the auto-hide-keyboard flag).
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core import sdk
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.mobile.system_actions import parse_system_action


# ---------------------------------------------------------------------------
# parse_system_action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction,kind,arg",
    [
        ("press back", "press_back", {}),
        ("Press the back button", "press_back", {}),
        ("go back", "press_back", {}),
        ("Rotate to landscape", "rotate", {"orientation": "landscape"}),
        ("rotate the screen to portrait", "rotate", {"orientation": "portrait"}),
        ("set orientation to landscape", "rotate", {"orientation": "landscape"}),
        ("Hide the keyboard", "hide_keyboard", {}),
        ("dismiss keyboard", "hide_keyboard", {}),
        ("open deep link myapp://settings", "deep_link", {"url": "myapp://settings"}),
        ("open url https://x.test/a", "deep_link", {"url": "https://x.test/a"}),
        ("background the app", "background_app", {}),
        ("background app for 5 seconds", "background_app", {"seconds": 5}),
        ("send the app to background", "background_app", {}),
        ("accept biometric", "accept_biometric", {}),
        ("approve the fingerprint prompt", "accept_biometric", {}),
        ("open notifications", "open_notification", {}),
        ("open the notification shade", "open_notification", {}),
        ("open notification titled Message from Bob", "open_notification", {"text": "Message from Bob"}),
    ],
)
def test_parse_system_action(instruction, kind, arg):
    action = parse_system_action(instruction)
    assert action is not None
    assert action.kind == kind
    assert action.arg == arg


def test_parse_system_action_ignores_normal_steps():
    assert parse_system_action("Press Back to Top") is None  # a real "Back to Top" control
    assert parse_system_action("Click Login") is None
    assert parse_system_action("Tap the Back arrow icon") is None
    assert parse_system_action("Verify keyboard is visible") is None


# ---------------------------------------------------------------------------
# AppiumAdapter.execute_system_action
# ---------------------------------------------------------------------------


class _FakeElement:
    def __init__(self):
        self.clicked = False

    def click(self):
        self.clicked = True


class _FakeDriver:
    def __init__(self, platform="Android"):
        self.capabilities = {"platformName": platform}
        self.calls: list[tuple] = []
        self.scripts: list[tuple] = []
        self._orientation = "PORTRAIT"
        self.notification_element = _FakeElement()

    def back(self):
        self.calls.append(("back",))

    def press_keycode(self, code):
        self.calls.append(("press_keycode", code))

    @property
    def orientation(self):
        return self._orientation

    @orientation.setter
    def orientation(self, value):
        self._orientation = value
        self.calls.append(("orientation", value))

    def hide_keyboard(self):
        self.calls.append(("hide_keyboard",))

    def get(self, url):
        self.calls.append(("get", url))

    def background_app(self, seconds):
        self.calls.append(("background_app", seconds))

    def open_notifications(self):
        self.calls.append(("open_notifications",))

    def execute_script(self, name, args=None):
        self.scripts.append((name, args or {}))

    def find_element(self, by, value):
        self.calls.append(("find_element", by, value))
        return self.notification_element


def _run_system(driver, kind, arg=None):
    adapter = AppiumAdapter(driver)
    return asyncio.run(adapter.execute_system_action(kind, arg or {}))


def test_press_back_android_uses_keycode():
    d = _FakeDriver("Android")
    _run_system(d, "press_back")
    assert ("press_keycode", 4) in d.calls


def test_press_back_ios_uses_back():
    d = _FakeDriver("iOS")
    _run_system(d, "press_back")
    assert ("back",) in d.calls


def test_rotate_sets_orientation():
    d = _FakeDriver("Android")
    out = _run_system(d, "rotate", {"orientation": "landscape"})
    assert ("orientation", "LANDSCAPE") in d.calls
    assert out["orientation"] == "LANDSCAPE"


def test_hide_keyboard():
    d = _FakeDriver("Android")
    _run_system(d, "hide_keyboard")
    assert ("hide_keyboard",) in d.calls


def test_deep_link_navigates():
    d = _FakeDriver("Android")
    _run_system(d, "deep_link", {"url": "myapp://x"})
    assert ("get", "myapp://x") in d.calls


def test_background_app_default_and_explicit_seconds():
    d = _FakeDriver("Android")
    _run_system(d, "background_app", {})
    assert ("background_app", 3) in d.calls
    d2 = _FakeDriver("Android")
    _run_system(d2, "background_app", {"seconds": 7})
    assert ("background_app", 7) in d2.calls


def test_accept_biometric_per_platform():
    a = _FakeDriver("Android")
    _run_system(a, "accept_biometric")
    assert a.scripts[-1][0] == "mobile: fingerprint"
    i = _FakeDriver("iOS")
    _run_system(i, "accept_biometric")
    assert i.scripts[-1][0] == "mobile: sendBiometricMatch"
    assert i.scripts[-1][1]["match"] is True


def test_open_notification_opens_shade_and_taps_text():
    d = _FakeDriver("Android")
    out = _run_system(d, "open_notification", {"text": "Message from Bob"})
    assert ("open_notifications",) in d.calls
    assert out["tapped"] is True
    assert d.notification_element.clicked is True
    # xpath uses the contains() literal for the text.
    find_calls = [c for c in d.calls if c[0] == "find_element"]
    assert "Message from Bob" in find_calls[-1][2]


def test_open_notification_no_text_just_opens():
    d = _FakeDriver("Android")
    out = _run_system(d, "open_notification", {})
    assert ("open_notifications",) in d.calls
    assert out["tapped"] is False


def test_unknown_system_action_raises():
    with pytest.raises(ValueError):
        _run_system(_FakeDriver(), "teleport")


# ---------------------------------------------------------------------------
# sdk.act routing
# ---------------------------------------------------------------------------


class _RoutingAdapter:
    """Captures whether a step went to the system path or the element path."""

    def __init__(self):
        self.system_calls: list[tuple] = []
        self.executed = False

    async def execute_system_action(self, kind, arg=None):
        self.system_calls.append((kind, arg))
        return {"detail": f"did {kind}"}

    # If grounding were reached these would be called; they should not be for
    # system verbs.
    async def collect_context(self, _req):
        from bubblegum.core.schemas import UIContext
        self.executed = True
        return UIContext(hierarchy_xml="<hierarchy/>", screen_signature="sig")


@pytest.mark.asyncio
async def test_act_routes_mobile_system_verb_before_grounding(monkeypatch):
    adapter = _RoutingAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Rotate to landscape", channel="mobile", driver=object())

    assert result.status == "passed"
    assert result.target.ref == "system:rotate"
    assert adapter.system_calls == [("rotate", {"orientation": "landscape"})]
    assert adapter.executed is False  # never grounded


@pytest.mark.asyncio
async def test_act_system_action_failure_is_reported(monkeypatch):
    class Boom(_RoutingAdapter):
        async def execute_system_action(self, kind, arg=None):
            raise RuntimeError("driver exploded")

    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: Boom())
    result = await sdk.act("press back", channel="mobile", driver=object())
    assert result.status == "failed"
    assert result.error.error_type == "MobileSystemActionError"


@pytest.mark.asyncio
async def test_explicit_action_type_bypasses_system_routing(monkeypatch):
    # "press back" with an explicit action_type should NOT be treated as a
    # system verb (caller opted into the element path).
    adapter = _RoutingAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    # Force a benign element path by stubbing the rest of the pipeline is heavy;
    # instead assert the system path was not taken by checking no system call
    # happens before grounding raises/returns. We just confirm routing skipped.
    try:
        await sdk.act("press back", channel="mobile", driver=object(), action_type="tap", selector="//x")
    except Exception:
        pass
    assert adapter.system_calls == []


@pytest.mark.asyncio
async def test_auto_hide_keyboard_flag(monkeypatch):
    cfg = BubblegumConfig()
    cfg.mobile.auto_hide_keyboard = True
    monkeypatch.setattr(sdk, "_config", cfg)

    hidden = {"count": 0}

    class Adapter:
        async def execute_system_action(self, kind, arg=None):
            if kind == "hide_keyboard":
                hidden["count"] += 1

    await sdk._maybe_hide_keyboard(Adapter(), "mobile", "tap")
    assert hidden["count"] == 1
    # No-op for web or non-tap.
    await sdk._maybe_hide_keyboard(Adapter(), "web", "tap")
    await sdk._maybe_hide_keyboard(Adapter(), "mobile", "type")
    assert hidden["count"] == 1
