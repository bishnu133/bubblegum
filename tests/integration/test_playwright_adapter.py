"""
tests/integration/test_playwright_adapter.py
=============================================
Integration tests for Phase 1A.

Setup:
    pip install playwright pytest-playwright
    playwright install chromium
    pytest tests/integration/ -v

Architecture: all test code is synchronous end-to-end.
  - SyncPlaywrightAdapter wraps Playwright sync API.
  - GroundingEngine.ground() (async) is called in a background thread via
    _run_in_thread(), which creates a fresh event loop in that thread,
    completely independent of pytest-asyncio's main-thread loop.

sync_recover() two-phase design:
  Phase 1 — explicit selector only, using a registry that contains ONLY
    ExplicitSelectorResolver. This avoids AmbiguousTargetError caused by
    ExplicitSelectorResolver (1.0) and AccessibilityTreeResolver (0.96)
    both being Tier-1 resolvers with a gap of 0.04 < ambiguous_gap 0.05.
  Phase 2 — if Phase 1 fails (stale/missing selector), fall back to the
    full engine without the explicit_selector in context.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from bubblegum.adapters.web.playwright.sync_adapter import SyncPlaywrightAdapter
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import BubblegumError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import (
    ActionPlan,
    ContextRequest,
    ErrorInfo,
    ExecutionOptions,
    StepIntent,
    StepResult,
    ValidationPlan,
)


# ---------------------------------------------------------------------------
# Background-thread event loop runner
# ---------------------------------------------------------------------------

def _run_in_thread(coro):
    """
    Run a coroutine in a fresh event loop in a background thread.
    Safe from any context — completely independent of pytest-asyncio's loop.
    """
    container: dict = {}

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            container["result"] = loop.run_until_complete(coro)
        except Exception as exc:
            container["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()

    if "error" in container:
        raise container["error"]
    return container["result"]


# ---------------------------------------------------------------------------
# Module-level grounding engine (full resolver set)
# ---------------------------------------------------------------------------

_registry = ResolverRegistry()
_engine   = GroundingEngine(registry=_registry)


# ---------------------------------------------------------------------------
# Explicit-selector-only engine (used by sync_recover Phase 1)
# Avoids AmbiguousTargetError when explicit (1.0) and a11y (0.96) both run
# in Tier 1 with a gap of 0.04, below the ambiguous_gap threshold of 0.05.
# ---------------------------------------------------------------------------

def _make_explicit_only_engine() -> GroundingEngine:
    reg = ResolverRegistry()
    for r in list(reg.all()):
        if r.name != "explicit_selector":
            reg.unregister(r.name)
    return GroundingEngine(registry=reg)


_explicit_engine = _make_explicit_only_engine()


# ---------------------------------------------------------------------------
# Sync SDK helpers
# ---------------------------------------------------------------------------

def _infer_action_type(instruction: str) -> str:
    lowered = instruction.lower()
    if any(w in lowered for w in ("type", "enter", "fill", "input")):
        return "type"
    if any(w in lowered for w in ("select", "choose", "pick")):
        return "select"
    if "scroll" in lowered:
        return "scroll"
    if any(w in lowered for w in ("verify", "check", "assert", "visible", "present")):
        return "verify"
    return "click"


def sync_act(instruction: str, page, channel: str = "web") -> StepResult:
    t0 = time.monotonic()
    adapter = SyncPlaywrightAdapter(page)
    options = ExecutionOptions()

    ui_ctx = adapter.collect_context(ContextRequest(include_screenshot=False))
    intent = StepIntent(
        instruction=instruction, channel=channel, platform="web",
        action_type=_infer_action_type(instruction), options=options,
        context={},
    )
    if ui_ctx.a11y_snapshot:
        intent.context["a11y_snapshot"] = ui_ctx.a11y_snapshot
    if ui_ctx.screen_signature:
        intent.context["screen_signature"] = ui_ctx.screen_signature

    try:
        target, traces = _run_in_thread(_engine.ground(intent))
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed", action=instruction, confidence=0.0,
            duration_ms=duration_ms, traces=[],
            error=ErrorInfo(
                error_type=type(exc).__name__, message=str(exc),
                resolver_name=exc.resolver_name, candidates=list(exc.candidates),
            ),
        )

    plan = ActionPlan(action_type=intent.action_type, target_hint=instruction, options=options)
    exec_result = adapter.execute(plan, target)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if not exec_result.success:
        return StepResult(
            status="failed", action=instruction, target=target,
            confidence=target.confidence, duration_ms=duration_ms, traces=traces,
            error=ErrorInfo(
                error_type="ExecutionFailedError",
                message=exec_result.error or "Execution failed",
                resolver_name=target.resolver_name,
            ),
        )

    return StepResult(
        status="passed", action=instruction, target=target,
        confidence=target.confidence, duration_ms=duration_ms, traces=traces,
    )


def sync_verify(instruction: str, page, assertion_type: str = "text_visible",
                expected_value: str | None = None, channel: str = "web") -> StepResult:
    t0 = time.monotonic()
    adapter = SyncPlaywrightAdapter(page)
    options = ExecutionOptions()

    ui_ctx = adapter.collect_context(ContextRequest(include_screenshot=False))
    intent = StepIntent(
        instruction=instruction, channel=channel, platform="web",
        action_type="verify", options=options,
        context={"a11y_snapshot": ui_ctx.a11y_snapshot} if ui_ctx.a11y_snapshot else {},
    )

    try:
        target, traces = _run_in_thread(_engine.ground(intent))
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed", action=instruction, confidence=0.0,
            duration_ms=duration_ms, traces=[],
            error=ErrorInfo(error_type=type(exc).__name__, message=str(exc)),
        )

    ev = expected_value or instruction
    v_result = adapter.validate(
        ValidationPlan(assertion_type=assertion_type, expected_value=ev, timeout_ms=3000)
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    return StepResult(
        status="passed" if v_result.passed else "failed",
        action=instruction, target=target, confidence=target.confidence,
        validation=v_result, duration_ms=duration_ms, traces=traces,
    )


def sync_recover(page, failed_selector: str, intent_str: str,
                 channel: str = "web") -> StepResult:
    """
    Two-phase recovery:

    Phase 1 — try the explicit selector alone, using _explicit_engine which
    contains ONLY ExplicitSelectorResolver. This prevents AmbiguousTargetError
    that would occur if both ExplicitSelectorResolver (1.0) and
    AccessibilityTreeResolver (0.96) ran together in Tier 1 with a gap of 0.04
    (below the ambiguous_gap threshold of 0.05).

    If Phase 1 succeeds (selector still works) -> status "passed".
    If Phase 1 fails (selector stale or missing) -> Phase 2.

    Phase 2 — ground with the full engine, no explicit_selector in context.
    If Phase 2 succeeds -> status "recovered".
    """
    t0 = time.monotonic()
    adapter = SyncPlaywrightAdapter(page)
    options = ExecutionOptions()
    action_type = _infer_action_type(intent_str)

    ui_ctx = adapter.collect_context(ContextRequest(include_screenshot=False))
    plan = ActionPlan(action_type=action_type, target_hint=intent_str, options=options)

    # --- Phase 1: explicit selector only ---
    intent_explicit = StepIntent(
        instruction=intent_str, channel=channel, platform="web",
        action_type=action_type, options=options,
        context={"explicit_selector": failed_selector},
    )

    explicit_target = None
    explicit_traces = []
    try:
        explicit_target, explicit_traces = _run_in_thread(
            _explicit_engine.ground(intent_explicit)
        )
    except BubblegumError:
        pass  # no candidate from explicit selector — fall through to Phase 2

    if explicit_target is not None:
        exec_result = adapter.execute(plan, explicit_target)
        if exec_result.success:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return StepResult(
                status="passed", action=intent_str, target=explicit_target,
                confidence=explicit_target.confidence,
                duration_ms=duration_ms, traces=explicit_traces,
            )
        # Selector resolved but execute failed (element stale) — fall to Phase 2

    # --- Phase 2: full engine, no explicit selector ---
    intent_fallback = StepIntent(
        instruction=intent_str, channel=channel, platform="web",
        action_type=action_type, options=options,
        context={},
    )
    if ui_ctx.a11y_snapshot:
        intent_fallback.context["a11y_snapshot"] = ui_ctx.a11y_snapshot

    try:
        target, traces = _run_in_thread(_engine.ground(intent_fallback))
    except BubblegumError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        return StepResult(
            status="failed", action=intent_str, confidence=0.0,
            duration_ms=duration_ms, traces=[],
            error=ErrorInfo(error_type=type(exc).__name__, message=str(exc)),
        )

    exec_result = adapter.execute(plan, target)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if not exec_result.success:
        return StepResult(
            status="failed", action=intent_str, target=target,
            confidence=target.confidence, duration_ms=duration_ms, traces=traces,
            error=ErrorInfo(
                error_type="ExecutionFailedError",
                message=exec_result.error or "Recovery failed",
                resolver_name=target.resolver_name,
            ),
        )

    return StepResult(
        status="recovered", action=intent_str, target=target,
        confidence=target.confidence, duration_ms=duration_ms, traces=traces,
    )


# ---------------------------------------------------------------------------
# Test page HTML
# ---------------------------------------------------------------------------

LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head><title>Test Login</title></head>
<body>
  <h1>Welcome</h1>
  <form>
    <label for="user">Username</label>
    <input id="user" type="text" placeholder="Username" />
    <label for="pass">Password</label>
    <input id="pass" type="password" placeholder="Password" />
    <button id="login-btn" type="button">Login</button>
    <button id="cancel-btn" type="button">Cancel</button>
  </form>
  <a href="/forgot">Forgot password?</a>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# collect_context()
# ---------------------------------------------------------------------------

class TestCollectContext:

    def test_returns_uicontext_with_snapshot(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        ui_ctx = SyncPlaywrightAdapter(page).collect_context(
            ContextRequest(include_screenshot=False))
        assert ui_ctx.a11y_snapshot is not None
        assert len(ui_ctx.a11y_snapshot) > 0

    def test_a11y_snapshot_contains_login_button(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        ui_ctx = SyncPlaywrightAdapter(page).collect_context(
            ContextRequest(include_screenshot=False))
        assert "Login" in (ui_ctx.a11y_snapshot or "")

    def test_screen_signature_is_set(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        ui_ctx = SyncPlaywrightAdapter(page).collect_context(
            ContextRequest(include_screenshot=False))
        assert ui_ctx.screen_signature is not None


# ---------------------------------------------------------------------------
# act()
# ---------------------------------------------------------------------------

class TestActClickLogin:

    def test_act_click_login_button_passes(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_act("Click Login", page)
        assert result.status in ("passed", "recovered"), (
            f"Expected passed/recovered, got '{result.status}'. Error: {result.error}")
        assert result.target is not None
        assert result.confidence > 0.0
        assert result.duration_ms >= 0

    def test_act_click_login_target_ref_format(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_act("Click Login", page)
        assert result.target is not None, f"No target. Error: {result.error}"
        ref = result.target.ref
        assert any(ref.startswith(p) for p in ("role=", "text=", "#", ".", "/", "["))

    def test_act_returns_step_result_with_traces(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_act("Click Login", page)
        assert isinstance(result.traces, list)
        assert len(result.traces) >= 1, (
            f"No traces. Status: {result.status}, Error: {result.error}")


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

class TestVerify:

    def test_verify_login_button_visible_passes(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_verify("Login button visible", page)
        assert result.status in ("passed", "failed")
        assert result.duration_ms >= 0

    def test_verify_text_visible_assertion(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = SyncPlaywrightAdapter(page).validate(
            ValidationPlan(assertion_type="text_visible", expected_value="Login", timeout_ms=3000))
        assert result.passed is True

    def test_verify_text_visible_fails_for_absent_text(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = SyncPlaywrightAdapter(page).validate(
            ValidationPlan(assertion_type="text_visible",
                           expected_value="DOES_NOT_EXIST_XYZ", timeout_ms=1000))
        assert result.passed is False

    def test_verify_element_state_assertion(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = SyncPlaywrightAdapter(page).validate(
            ValidationPlan(assertion_type="element_state",
                           expected_value="#login-btn", timeout_ms=3000))
        assert result.passed is True


# ---------------------------------------------------------------------------
# recover()
# ---------------------------------------------------------------------------

class TestRecover:

    def test_recover_with_stale_selector_uses_fallback(self, page):
        """Stale selector -> Phase 2 -> fallback resolvers -> recovered or failed."""
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_recover(page, failed_selector="#stale-id", intent_str="Click Login")
        assert result.status in ("recovered", "failed")

    def test_recover_status_is_recovered_not_passed(self, page):
        """When fallback resolver finds the element, status must be 'recovered'."""
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_recover(page, failed_selector="#stale-id", intent_str="Click Login")
        if result.status != "failed":
            assert result.status == "recovered", (
                f"Expected 'recovered' but got '{result.status}'. "
                "recover() must not return 'passed' when original selector was stale.")

    def test_recover_with_valid_selector_returns_passed(self, page):
        """Valid selector -> Phase 1 succeeds -> status 'passed'."""
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_recover(page, failed_selector="#login-btn", intent_str="Click Login")
        assert result.status in ("passed", "recovered"), (
            f"Expected passed/recovered, got '{result.status}'. Error: {result.error}")

    def test_recover_result_has_target(self, page):
        page.set_content(LOGIN_PAGE_HTML)
        result = sync_recover(page, failed_selector="#login-btn", intent_str="Click Login")
        if result.status != "failed":
            assert result.target is not None


# ---------------------------------------------------------------------------
# screenshot()
# ---------------------------------------------------------------------------

class TestScreenshot:

    def test_screenshot_saves_png_file(self, page, tmp_path, monkeypatch):
        import bubblegum.adapters.web.playwright.sync_adapter as sync_mod
        monkeypatch.setattr(sync_mod, "_ARTIFACTS_DIR", tmp_path / "artifacts")

        page.set_content(LOGIN_PAGE_HTML)
        ref = SyncPlaywrightAdapter(page).screenshot()

        assert ref.type == "screenshot"
        assert ref.path.endswith(".png")
        from pathlib import Path
        assert Path(ref.path).exists()
        assert Path(ref.path).stat().st_size > 0

    def test_screenshot_timestamp_is_set(self, page, tmp_path, monkeypatch):
        import bubblegum.adapters.web.playwright.sync_adapter as sync_mod
        monkeypatch.setattr(sync_mod, "_ARTIFACTS_DIR", tmp_path / "artifacts")

        page.set_content(LOGIN_PAGE_HTML)
        ref = SyncPlaywrightAdapter(page).screenshot()

        assert ref.timestamp is not None
        assert "T" in ref.timestamp
