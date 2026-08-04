"""iOS / native system-alert auto-handling.

OS permission dialogs (notifications, location, camera, ATT, …) live in a
separate process and often aren't in the app's page source, so name-based
grounding can't tap them. The engine clears them via the W3C alert API when
`grounding.system_alert_handling` is "accept"/"dismiss". Tested with a fake
driver/adapter — no device.
"""

from __future__ import annotations

import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core import sdk
from bubblegum.core.config import BubblegumConfig


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Fake Appium driver with a W3C alert
# ----------------------------------------------------------------------

class _FakeAlert:
    def __init__(self, text="Allow “App” to send you notifications?",
                 raise_on_text=False, raise_on_action=False):
        self._text = text
        self._raise_on_text = raise_on_text
        self._raise_on_action = raise_on_action
        self.accepted = False
        self.dismissed = False

    @property
    def text(self):
        if self._raise_on_text:
            raise Exception("no such alert")
        return self._text

    def accept(self):
        if self._raise_on_action:
            raise Exception("accept failed")
        self.accepted = True

    def dismiss(self):
        if self._raise_on_action:
            raise Exception("dismiss failed")
        self.dismissed = True


class _SwitchTo:
    def __init__(self, alert):
        self.alert = alert


class _FakeDriver:
    def __init__(self, alert):
        self.capabilities = {"platformName": "iOS"}
        self.switch_to = _SwitchTo(alert)


# ----------------------------------------------------------------------
# AppiumAdapter.handle_system_alert
# ----------------------------------------------------------------------

def test_accept_alert_when_present():
    alert = _FakeAlert()
    adapter = AppiumAdapter(_FakeDriver(alert))
    r = adapter.handle_system_alert("accept")
    assert r["handled"] is True and r["mode"] == "accept"
    assert alert.accepted is True and alert.dismissed is False
    assert "notifications" in r["text"]


def test_dismiss_alert_when_present():
    alert = _FakeAlert()
    adapter = AppiumAdapter(_FakeDriver(alert))
    r = adapter.handle_system_alert("dismiss")
    assert r["handled"] is True and alert.dismissed is True and alert.accepted is False


def test_no_alert_present_is_not_an_error():
    alert = _FakeAlert(raise_on_text=True)
    adapter = AppiumAdapter(_FakeDriver(alert))
    r = adapter.handle_system_alert("accept")
    assert r["handled"] is False and r["text"] is None
    assert alert.accepted is False


def test_alert_action_failure_is_swallowed():
    alert = _FakeAlert(raise_on_action=True)
    adapter = AppiumAdapter(_FakeDriver(alert))
    r = adapter.handle_system_alert("accept")
    assert r["handled"] is False and "error" in r


# ----------------------------------------------------------------------
# SDK gate: _maybe_handle_system_alert
# ----------------------------------------------------------------------

class _AlertAdapter:
    def __init__(self, result):
        self._result = result
        self.calls: list[str] = []

    def handle_system_alert(self, mode):
        self.calls.append(mode)
        return dict(self._result, mode=mode)


def test_config_default_is_ignore():
    assert BubblegumConfig().grounding.system_alert_handling == "ignore"


def test_sdk_ignore_does_not_call_adapter(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "system_alert_handling", "ignore")
    ad = _AlertAdapter({"handled": True})
    assert _run(sdk._maybe_handle_system_alert(ad, "mobile")) is None
    assert ad.calls == []


def test_sdk_accept_calls_adapter(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "system_alert_handling", "accept")
    ad = _AlertAdapter({"handled": True, "text": "Allow"})
    r = _run(sdk._maybe_handle_system_alert(ad, "mobile"))
    assert r["handled"] is True
    assert ad.calls == ["accept"]


def test_sdk_dismiss_mode(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "system_alert_handling", "dismiss")
    ad = _AlertAdapter({"handled": False})
    _run(sdk._maybe_handle_system_alert(ad, "mobile"))
    assert ad.calls == ["dismiss"]


def test_sdk_noop_on_web(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "system_alert_handling", "accept")
    ad = _AlertAdapter({"handled": True})
    assert _run(sdk._maybe_handle_system_alert(ad, "web")) is None
    assert ad.calls == []


def test_sdk_adapter_without_handler_is_safe(monkeypatch):
    monkeypatch.setattr(sdk._config.grounding, "system_alert_handling", "accept")

    class _Bare:
        pass

    assert _run(sdk._maybe_handle_system_alert(_Bare(), "mobile")) is None
