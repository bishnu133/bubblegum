"""
Unit coverage for the bridge mobile-attach (client-owned Appium session) path.

Exercises the pure pieces — ``OpenSpec`` parsing/validation, the
``attach_to_appium_session`` newSession-intercept logic against a fake Appium
webdriver module, and capability advertisement — with no real Appium server or
device. The live attach is integration-only.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from bubblegum.bridge import protocol as p
from bubblegum.bridge.handlers import build_server
from bubblegum.bridge.sessions import OpenSpec, OpenedSession


# --- OpenSpec parsing -----------------------------------------------------
def test_openspec_parses_existing_session_id():
    spec = OpenSpec.from_params(
        {"channel": "mobile", "appium_url": "http://h/wd/hub", "existing_session_id": "abc123"}
    )
    assert spec.existing_session_id == "abc123"


def test_openspec_existing_session_id_on_web_is_invalid():
    with pytest.raises(p.BridgeError) as exc:
        OpenSpec.from_params({"channel": "web", "existing_session_id": "abc"})
    assert exc.value.code == p.INVALID_PARAMS


def test_openspec_existing_session_id_defaults_none():
    spec = OpenSpec.from_params({"channel": "mobile", "appium_url": "http://h"})
    assert spec.existing_session_id is None


# --- capability + wiring --------------------------------------------------
@pytest.mark.asyncio
async def test_handshake_advertises_mobile_attach_capability():
    server, _ = build_server()
    raw = await server.handle_message(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "handshake"})
    )
    caps = json.loads(raw)["result"]["capabilities"]
    assert "channel.mobile.attach" in caps


@pytest.mark.asyncio
async def test_session_open_forwards_existing_session_id_to_factory():
    seen: dict[str, object] = {}

    async def factory(spec: OpenSpec) -> OpenedSession:
        seen["existing_session_id"] = spec.existing_session_id

        async def aclose() -> None:
            return None

        return OpenedSession(session=object(), aclose=aclose)

    server, _ = build_server(factory=factory)
    raw = await server.handle_message(
        json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "session.open",
            "params": {
                "channel": "mobile",
                "appium_url": "http://h/wd/hub",
                "existing_session_id": "sess-xyz",
            },
        })
    )
    assert "session_id" in json.loads(raw)["result"]
    assert seen == {"existing_session_id": "sess-xyz"}


# --- attach_to_appium_session intercept logic -----------------------------
class _FakeRemote:
    """Stand-in for appium.webdriver.Remote that records the newSession result.

    Its ``__init__`` mimics the real one: it calls ``self.execute("newSession")``,
    which the attach helper has monkeypatched to short-circuit.
    """

    execute = None  # replaced per-instance-class by the helper's patch

    def __init__(self, command_executor, options=None):
        self.command_executor = command_executor
        self.options = options
        self.session_id = None
        # The real Remote issues newSession during construction; emulate that so
        # the helper's intercept is exercised.
        result = type(self).execute(self, "newSession", {})
        self.session_id = result.get("sessionId")


def _install_fake_appium(monkeypatch):
    appium_mod = types.ModuleType("appium")
    webdriver_mod = types.ModuleType("appium.webdriver")
    webdriver_mod.Remote = _FakeRemote
    appium_mod.webdriver = webdriver_mod
    monkeypatch.setitem(sys.modules, "appium", appium_mod)
    monkeypatch.setitem(sys.modules, "appium.webdriver", webdriver_mod)
    return webdriver_mod


def test_attach_intercepts_new_session_and_sets_id(monkeypatch):
    from bubblegum.testing import appium_driver

    webdriver_mod = _install_fake_appium(monkeypatch)
    # Avoid building real platform options; a bare options object is fine here.
    monkeypatch.setattr(appium_driver, "_bare_appium_options", lambda: object())

    driver = appium_driver.attach_to_appium_session(
        "http://host/wd/hub", "live-session-42", caps={}
    )
    assert driver.session_id == "live-session-42"
    # The real dispatch must be restored so later drivers create sessions normally.
    assert webdriver_mod.Remote.execute is _FakeRemote.__dict__["execute"] or \
        webdriver_mod.Remote.execute is None


def test_attach_restores_execute_even_on_error(monkeypatch):
    from bubblegum.testing import appium_driver

    webdriver_mod = _install_fake_appium(monkeypatch)
    original = webdriver_mod.Remote.execute
    monkeypatch.setattr(appium_driver, "_bare_appium_options", lambda: object())

    def _boom(self, command_executor, options=None):
        raise RuntimeError("connect failed")

    monkeypatch.setattr(webdriver_mod.Remote, "__init__", _boom)
    with pytest.raises(RuntimeError):
        appium_driver.attach_to_appium_session("http://host", "s", caps={})
    # execute() restored to the original despite the constructor blowing up.
    assert webdriver_mod.Remote.execute is original
