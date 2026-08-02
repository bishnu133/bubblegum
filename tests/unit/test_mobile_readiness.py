"""M-D: mobile readiness & resilience.

Covers the pure signals (``detect_mobile_readiness`` / ``classify_driver_error``
/ ``readiness_failure_message``), the progress-aware + ANR/crash-early-return
``AppiumAdapter.wait_until_stable`` (fake driver — no server), and the SDK health
gate that fails a step cleanly when the app is wedged.
"""

from __future__ import annotations

import asyncio
import time

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter, _sanitize_retry_reason
from bubblegum.core import sdk
from bubblegum.core.mobile.readiness import (
    classify_driver_error,
    detect_mobile_readiness,
    readiness_failure_message,
)
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# detect_mobile_readiness
# ----------------------------------------------------------------------

def test_ready_screen_has_no_blocker():
    r = detect_mobile_readiness(hierarchy_xml="<hierarchy><node text='Home'/></hierarchy>", platform="android")
    assert r["ready"] is True
    assert r["blocker"] == "none"


def test_progress_indicator_detected():
    r = detect_mobile_readiness(
        hierarchy_xml="<hierarchy><android.widget.ProgressBar/></hierarchy>", platform="android"
    )
    assert r["progress_active"] is True
    assert r["blocker"] == "progress"
    assert r["ready"] is False


def test_anr_dialog_detected():
    r = detect_mobile_readiness(
        hierarchy_xml="<hierarchy><node text=\"Demo isn't responding\"/><node text='Wait'/></hierarchy>",
        platform="android",
    )
    assert r["anr_detected"] is True
    assert r["blocker"] == "anr"


def test_crash_dialog_detected():
    r = detect_mobile_readiness(
        hierarchy_xml="<hierarchy><node text='Demo has stopped'/></hierarchy>", platform="android"
    )
    assert r["crash_detected"] is True
    assert r["blocker"] == "crash"


def test_crash_outranks_progress_and_anr():
    xml = "<hierarchy><android.widget.ProgressBar/><node text=\"App isn't responding\"/><node text='App has stopped'/></hierarchy>"
    r = detect_mobile_readiness(hierarchy_xml=xml, platform="android")
    assert r["blocker"] == "crash"  # hard blocker precedence


def test_unfortunately_alone_is_not_a_crash():
    # Ordinary in-app copy must not be mistaken for a crash dialog.
    r = detect_mobile_readiness(
        hierarchy_xml="<hierarchy><node text='Unfortunately this offer has expired'/></hierarchy>",
        platform="android",
    )
    assert r["crash_detected"] is False
    assert r["ready"] is True


def test_empty_hierarchy_is_ready():
    assert detect_mobile_readiness(hierarchy_xml="", platform="android")["ready"] is True


# ----------------------------------------------------------------------
# classify_driver_error + retry-reason labeling
# ----------------------------------------------------------------------

def test_classify_session_lost():
    assert classify_driver_error("A session is either terminated or not started") == "session_lost"
    assert classify_driver_error("invalid session id") == "session_lost"


def test_classify_transient():
    assert classify_driver_error("stale element reference: element is not attached") == "transient"


def test_classify_other():
    assert classify_driver_error("some unrelated failure") == "other"


def test_sanitize_retry_reason_labels_session_lost():
    assert _sanitize_retry_reason(Exception("invalid session id: xyz")) == "session_lost"


def test_readiness_failure_message_is_actionable():
    anr = readiness_failure_message({"blocker": "anr"}, instruction="Tap Login")
    assert "not responding" in anr.lower()
    crash = readiness_failure_message({"blocker": "crash"})
    assert "crash" in crash.lower()


# ----------------------------------------------------------------------
# AppiumAdapter.wait_until_stable (fake driver)
# ----------------------------------------------------------------------

class _WaitDriver:
    def __init__(self, dumps):
        self.capabilities = {"platformName": "Android"}
        self._dumps = list(dumps)
        self._i = 0

    @property
    def page_source(self):
        val = self._dumps[min(self._i, len(self._dumps) - 1)]
        self._i += 1
        return val


def test_wait_until_stable_returns_stable_when_quiet():
    driver = _WaitDriver(["<hierarchy><node text='Home'/></hierarchy>"] * 5)
    adapter = AppiumAdapter(driver)
    diag = _run(adapter.wait_until_stable(quiet_ms=10, timeout_ms=1000))
    assert diag["outcome"] == "stable"
    assert diag["blocker"] == "none"


def test_wait_until_stable_early_returns_on_anr():
    driver = _WaitDriver(["<hierarchy><node text=\"Demo isn't responding\"/></hierarchy>"] * 5)
    adapter = AppiumAdapter(driver)
    diag = _run(adapter.wait_until_stable(quiet_ms=10, timeout_ms=1000))
    assert diag["outcome"] == "anr"
    assert diag["blocker"] == "anr"


def test_wait_until_stable_keeps_waiting_through_progress():
    # Hierarchy is quiet but a spinner is up the whole time -> never "stable",
    # times out (bounded) with the progress blocker recorded.
    driver = _WaitDriver(["<hierarchy><android.widget.ProgressBar/></hierarchy>"] * 50)
    adapter = AppiumAdapter(driver)
    diag = _run(adapter.wait_until_stable(quiet_ms=10, timeout_ms=150))
    assert diag["outcome"] == "timeout"
    assert diag["blocker"] == "progress"


# ----------------------------------------------------------------------
# SDK health gate
# ----------------------------------------------------------------------

def _intent_with_readiness(readiness: dict | None) -> StepIntent:
    intent = StepIntent(
        instruction="Tap Login",
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase="Login",
        options=ExecutionOptions(),
    )
    app_state = {"channel": "mobile"}
    if readiness is not None:
        app_state["readiness"] = readiness
    intent.context["app_state"] = app_state
    return intent


def test_health_gate_fails_on_crash():
    intent = _intent_with_readiness({"blocker": "crash", "evidence": ["crash:has stopped"]})
    res = sdk._maybe_blocked_by_mobile_health(intent, "mobile", intent.instruction, time.monotonic())
    assert res is not None
    assert res.status == "failed"
    assert res.error.error_type == "AppNotReadyError"
    assert "crash" in res.error.message.lower()


def test_health_gate_fails_on_anr():
    intent = _intent_with_readiness({"blocker": "anr", "evidence": []})
    res = sdk._maybe_blocked_by_mobile_health(intent, "mobile", intent.instruction, time.monotonic())
    assert res is not None and res.status == "failed"


def test_health_gate_passes_when_ready():
    intent = _intent_with_readiness({"blocker": "none"})
    assert sdk._maybe_blocked_by_mobile_health(intent, "mobile", intent.instruction, time.monotonic()) is None


def test_health_gate_ignores_progress():
    # A spinner is not a hard blocker at the SDK gate (the stability wait handles it).
    intent = _intent_with_readiness({"blocker": "progress"})
    assert sdk._maybe_blocked_by_mobile_health(intent, "mobile", intent.instruction, time.monotonic()) is None


def test_health_gate_noop_on_web():
    intent = _intent_with_readiness({"blocker": "crash"})
    assert sdk._maybe_blocked_by_mobile_health(intent, "web", intent.instruction, time.monotonic()) is None
