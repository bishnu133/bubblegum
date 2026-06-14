"""
bubblegum/adapters/mobile/appium/adapter.py
===========================================
AppiumAdapter — implements BaseAdapter for Appium (mobile channel).

Wraps an Appium WebDriver session and exposes the same four async methods as
PlaywrightAdapter so the orchestration layer treats web and mobile uniformly.

collect_context():
    Captures hierarchy XML via driver.page_source.
    Computes screen_signature using compute_signature(activity, hierarchy_xml)
    where activity = driver.current_activity (Android) or bundle_id (iOS).
    Screenshot bytes captured when request.include_screenshot is True.

execute():
    Dispatches on plan.action_type → tap, type, scroll, swipe.
    target.ref is a dict: {"by": "xpath", "value": "//android.widget.Button[@text='Login']"}
    Falls back to find_element(AppiumBy.XPATH, ...) for all ref formats.

validate():
    Supports assertion_type: "text_visible" | "element_state" | "activity"
    "text_visible"  — page_source contains expected_value
    "element_state" — XPath element found and displayed
    "activity"      — driver.current_activity contains expected_value

screenshot():
    driver.get_screenshot_as_png() → saved to artifacts/<timestamp>.png → ArtifactRef.

Phase 4 — fully implemented.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import json

from bubblegum.adapters.base import BaseAdapter
from bubblegum.core.memory.fingerprint import compute_signature
from bubblegum.core.mobile.framework_detector import detect_mobile_surface
from bubblegum.core.mobile.system_dialog import detect_system_dialog
from bubblegum.core.mobile.system_dialog_guardrails import evaluate_system_dialog_guardrails
from bubblegum.core.mobile.scroll_discovery import build_mobile_scroll_discovery_plan
from bubblegum.core.mobile.system_dialog_actions import execute_system_dialog_action, resolve_system_dialog_action_candidate
from bubblegum.core.mobile.webview_diagnostics import build_webview_switch_diagnostics
from bubblegum.core.mobile.webview_guardrails import evaluate_webview_switch_guardrails
from bubblegum.core.mobile.webview_switch_eligibility import evaluate_webview_switch_eligibility
from bubblegum.core.mobile.webview_context_selection import select_webview_context
from bubblegum.core.mobile.webview_readiness import build_webview_readiness_plan
from bubblegum.core.mobile.webview_switch_config import is_webview_switching_enabled_for_operation
from bubblegum.core.mobile.webview_real_driver_switch import (
    build_real_webview_context_map,
    execute_real_driver_switch_with_ref,
    resolve_real_webview_context_ref,
)
from bubblegum.core.schemas import (
    ActionPlan,
    ArtifactRef,
    ContextRequest,
    ExecutionResult,
    ResolvedTarget,
    UIContext,
    ValidationPlan,
    ValidationResult,
)

logger = logging.getLogger(__name__)
_TRANSIENT_ERROR_MARKERS = (
    "stale element reference",
    "no such element",
    "element not interactable",
    "timeout",
    "could not be located",
)

_MAX_RETRY_CAP = 1
_RETRY_DELAY_SECONDS = 0.05

# Default press-and-hold duration for the long_press gesture (M1).
_LONG_PRESS_DEFAULT_MS = 1_000


def _is_transient_execution_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def _retry_budget(retry_count: int | None) -> int:
    if retry_count is None:
        return 0
    return max(0, min(int(retry_count), _MAX_RETRY_CAP))


def _sanitize_retry_reason(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    lower = text.lower()
    if "stale element reference" in lower:
        return "stale_element_reference"
    if "no such element" in lower or "could not be located" in lower:
        return "no_such_element"
    if "element not interactable" in lower:
        return "element_not_interactable"
    if "timeout" in lower:
        return "timeout"
    return "non_transient_error"






def _sanitize_context_type(context_name: object) -> str:
    value = str(context_name or "").strip().upper()
    if value == "NATIVE_APP":
        return "native"
    if value.startswith("WEBVIEW"):
        return "webview"
    if value == "CHROMIUM":
        return "webview/chromium"
    return "other"


def _infer_context_mode(has_native: bool, has_webview: bool, available_count: int) -> str:
    if has_native and has_webview:
        return "hybrid"
    if has_native and not has_webview:
        return "native_only"
    if has_webview and not has_native:
        return "webview_only"
    if available_count > 0:
        return "unknown"
    return "unknown"



def _safe_wiring_reason(value: object) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {
        "disabled_by_config",
        "mode_off",
        "operation_not_allowed",
        "enabled",
        "missing_eligibility",
        "eligibility_not_allowed",
        "missing_context_selection",
        "context_not_selected",
        "selected_context_type_not_webview",
        "switch_ready",
    }
    return normalized if normalized in allowed else "unknown"


def _safe_ms(value: object, *, default: int = 0) -> int:
    try:
        out = int(value)
    except Exception:
        return default
    return max(0, out)

_ARTIFACTS_DIR = Path("artifacts")


class AppiumAdapter(BaseAdapter):
    """
    Appium-based adapter for the mobile channel (Android / iOS).

    Args:
        driver: An Appium WebDriver instance (appium.webdriver.Remote or
                selenium.webdriver.Remote initialised with Appium capabilities).
                The adapter does NOT import Appium at module level so the package
                remains installable without appium-python-client.
    """

    channel:  str = "mobile"
    platform: str = "android"   # overridden at runtime from capabilities

    def __init__(self, driver) -> None:
        self._driver = driver
        # Detect platform from capabilities if available
        try:
            caps = driver.capabilities or {}
            plat = (caps.get("platformName") or caps.get("platform") or "android")
            self.platform = plat.lower()
        except Exception:
            self.platform = "android"
        self._webview_get_current_context = None
        self._webview_switch_context = None
        self._webview_restore_context = None
        self._webview_validate_operation = None
        self._webview_extract_operation = None
        self._webview_validate_metadata = None
        self._last_webview_switch_execution = None

    # ------------------------------------------------------------------
    # BaseAdapter implementation
    # ------------------------------------------------------------------

    async def wait_until_stable(
        self,
        *,
        quiet_ms: int = 400,
        timeout_ms: int = 5_000,
        spinner_selectors: list[str] | None = None,
    ) -> dict:
        """Wait until the UI hierarchy settles before resolution (W2).

        Re-polls ``driver.page_source`` until it stops changing for ``quiet_ms``
        (i.e. consecutive dumps are identical across that window), bounded by
        ``timeout_ms``. ``spinner_selectors`` is accepted for signature parity
        with the web adapter but not used on mobile. Best-effort: returns a
        diagnostic dict and never raises.
        """
        diag: dict = {"adapter": "appium", "quiet_ms": quiet_ms, "timeout_ms": timeout_ms}
        start = time.monotonic()
        deadline = start + max(timeout_ms, 0) / 1000.0
        poll_s = min(0.1, max(quiet_ms, 1) / 1000.0)
        last_dump: str | None = None
        last_change = start
        polls = 0

        while time.monotonic() < deadline:
            try:
                dump = self._driver.page_source
            except Exception as exc:
                diag.update({"outcome": "error", "polls": polls, "error": str(exc)})
                return diag
            polls += 1
            now = time.monotonic()
            if dump != last_dump:
                last_dump = dump
                last_change = now
            elif (now - last_change) * 1000.0 >= quiet_ms:
                diag.update({"outcome": "stable", "polls": polls, "waited_ms": int((now - start) * 1000)})
                return diag
            await asyncio.sleep(poll_s)

        diag.update({"outcome": "timeout", "polls": polls, "waited_ms": int((time.monotonic() - start) * 1000)})
        return diag

    async def collect_context(self, request: ContextRequest) -> UIContext:
        """
        Capture UIContext from the current Appium session.

        hierarchy_xml:    driver.page_source (XML element hierarchy)
        screenshot:       driver.get_screenshot_as_png() when requested
        screen_signature: SHA-256 of current_activity + hierarchy_xml
        """
        hierarchy_xml: str | None = None
        screenshot:    bytes | None = None

        try:
            if request.include_hierarchy or request.include_accessibility:
                hierarchy_xml = self._driver.page_source
        except Exception as exc:
            logger.warning("AppiumAdapter: page_source failed: %s", exc)

        try:
            if request.include_screenshot:
                screenshot = self._driver.get_screenshot_as_png()
        except Exception as exc:
            logger.warning("AppiumAdapter: get_screenshot_as_png() failed: %s", exc)

        # Use current_activity as the "URL" equivalent for Android;
        # fall back to a stable placeholder for iOS (no current_activity).
        activity = self._get_activity()
        sig = compute_signature(activity, hierarchy_xml)

        app_state: dict[str, object] = {}
        context_inventory = self._collect_context_inventory_metadata()
        if context_inventory:
            app_state["context_inventory"] = context_inventory

        app_state["framework_detection"] = detect_mobile_surface(
            platform=self.platform,
            capabilities=self._safe_capabilities(),
            app_state=app_state,
            hierarchy_xml=hierarchy_xml,
        )
        app_state["webview_switch_diagnostics"] = build_webview_switch_diagnostics(
            context_inventory=context_inventory,
            framework_detection=app_state.get("framework_detection") if isinstance(app_state.get("framework_detection"), dict) else None,
        )
        app_state["webview_switch_guardrails"] = evaluate_webview_switch_guardrails(
            context_inventory=context_inventory,
            framework_detection=app_state.get("framework_detection") if isinstance(app_state.get("framework_detection"), dict) else None,
            webview_switch_diagnostics=app_state.get("webview_switch_diagnostics") if isinstance(app_state.get("webview_switch_diagnostics"), dict) else None,
            explicit_opt_in=False,
        )
        app_state["system_dialog_detection"] = detect_system_dialog(
            platform=self.platform,
            capabilities=self._safe_capabilities(),
            app_state=app_state,
            hierarchy_xml=hierarchy_xml,
        )
        app_state["webview_switch_eligibility"] = evaluate_webview_switch_eligibility(
            instruction=None,
            context_inventory=context_inventory,
            framework_detection=app_state.get("framework_detection") if isinstance(app_state.get("framework_detection"), dict) else None,
            webview_switch_diagnostics=app_state.get("webview_switch_diagnostics") if isinstance(app_state.get("webview_switch_diagnostics"), dict) else None,
            webview_switch_guardrails=app_state.get("webview_switch_guardrails") if isinstance(app_state.get("webview_switch_guardrails"), dict) else None,
            system_dialog_detection=app_state.get("system_dialog_detection") if isinstance(app_state.get("system_dialog_detection"), dict) else None,
            explicit_opt_in=False,
            mode="dry_run",
        )
        app_state["webview_context_selection"] = select_webview_context(
            context_inventory=context_inventory,
            webview_switch_eligibility=app_state.get("webview_switch_eligibility") if isinstance(app_state.get("webview_switch_eligibility"), dict) else None,
            selection_policy="single_webview_only",
            preferred_context_hint=None,
        )
        app_state["system_dialog_guardrails"] = evaluate_system_dialog_guardrails(
            system_dialog_detection=app_state.get("system_dialog_detection") if isinstance(app_state.get("system_dialog_detection"), dict) else None,
            explicit_opt_in=False,
        )
        app_state["scroll_discovery"] = build_mobile_scroll_discovery_plan(
            instruction=None,
            target_hint=None,
            hierarchy_xml=hierarchy_xml,
            platform=self.platform,
            app_state=app_state,
            max_scrolls=3,
        )

        return UIContext(
            hierarchy_xml=hierarchy_xml,
            screenshot=screenshot,
            screen_signature=sig,
            app_state=app_state,
        )

    def _safe_capabilities(self) -> dict[str, object]:
        try:
            caps = self._driver.capabilities or {}
            if isinstance(caps, dict):
                return dict(caps)
        except Exception:
            return {}
        return {}

    def _collect_context_inventory_metadata(self) -> dict[str, object]:
        warnings: list[str] = []
        contexts: list[object] = []

        try:
            raw_contexts = self._driver.contexts
            if isinstance(raw_contexts, (list, tuple, set)):
                contexts = list(raw_contexts)
            elif raw_contexts is None:
                contexts = []
            else:
                contexts = [raw_contexts]
        except AttributeError:
            warnings.append("contexts_unavailable")
        except Exception:
            warnings.append("contexts_lookup_failed")

        available_context_count = len(contexts)
        context_types = sorted({_sanitize_context_type(ctx) for ctx in contexts})

        current_context_type = "other"
        try:
            current_context_type = _sanitize_context_type(self._driver.current_context)
        except AttributeError:
            warnings.append("current_context_unavailable")
            current_context_type = "unknown"
        except Exception:
            warnings.append("current_context_lookup_failed")
            current_context_type = "unknown"

        has_native_context = "native" in context_types
        webview_context_count = sum(1 for ctx in contexts if _sanitize_context_type(ctx) in {"webview", "webview/chromium"})
        has_webview_context = webview_context_count > 0

        return {
            "available_context_count": available_context_count,
            "context_types": context_types,
            "current_context_type": current_context_type,
            "has_native_context": has_native_context,
            "has_webview_context": has_webview_context,
            "webview_context_count": webview_context_count,
            "inferred_context_mode": _infer_context_mode(has_native_context, has_webview_context, available_context_count),
            "warnings": warnings,
            "safe_metadata_only": True,
        }

    async def execute(self, plan: ActionPlan, target: ResolvedTarget) -> ExecutionResult:
        """
        Perform the action described in plan against the resolved Appium element.

        target.ref must be a dict:  {"by": "xpath", "value": "//android.widget.Button[@text='Login']"}
        Supported by values: "xpath", "id", "accessibility id", "class name".

        Supported action_types: tap, click (alias), type, scroll, swipe.
        """
        t0 = time.monotonic()
        ref = target.ref

        retries = _retry_budget(getattr(plan.options, "retry_count", 0))
        attempts = 0
        last_exc: Exception | None = None
        last_transient = False

        wait_for = getattr(plan.options, "wait_for", None)
        wait_mode = str(wait_for).strip().lower() if wait_for else None
        wait_used = bool(wait_mode)

        while True:
            attempts += 1
            try:
                element = self._find_element(ref)
                wait_start = time.monotonic()
                self._wait_for_mode(ref=ref, element=element, wait_for=wait_for, timeout_ms=getattr(plan.options, "timeout_ms", 10_000))
                wait_duration_ms = int((time.monotonic() - wait_start) * 1000)
                if wait_used:
                    target.metadata["wait_used"] = True
                    target.metadata["wait_mode"] = wait_mode
                    target.metadata["wait_outcome"] = "success"
                    target.metadata["wait_adapter"] = "appium"
                    target.metadata["wait_duration_ms"] = wait_duration_ms
                self._execute_action(plan=plan, element=element)

                duration_ms = int((time.monotonic() - t0) * 1000)
                target.metadata["retry_attempts"] = max(0, attempts - 1)
                target.metadata["retry_transient"] = bool(last_transient)
                target.metadata["retry_reason"] = _sanitize_retry_reason(last_exc) if last_exc else "none"
                target.metadata["retry_adapter"] = "appium"
                return ExecutionResult(
                    success=True,
                    duration_ms=duration_ms,
                    element_ref=str(ref)
                )
            except Exception as exc:
                last_exc = exc
                last_transient = _is_transient_execution_error(exc)
                if attempts <= retries and last_transient:
                    logger.info(
                        "AppiumAdapter.execute transient failure (attempt %s/%s): %s",
                        attempts,
                        retries + 1,
                        exc,
                    )
                    time.sleep(_RETRY_DELAY_SECONDS)
                    continue

                duration_ms = int((time.monotonic() - t0) * 1000)
                logger.error("AppiumAdapter.execute failed ref=%r: %s", ref, exc)
                if wait_used:
                    target.metadata["wait_used"] = True
                    target.metadata["wait_mode"] = wait_mode
                    target.metadata["wait_outcome"] = "failed"
                    target.metadata["wait_adapter"] = "appium"
                target.metadata["retry_attempts"] = max(0, attempts - 1)
                target.metadata["retry_transient"] = bool(last_transient)
                target.metadata["retry_reason"] = _sanitize_retry_reason(exc)
                target.metadata["retry_adapter"] = "appium"
                return ExecutionResult(
                    success=False,
                    duration_ms=duration_ms,
                    element_ref=str(ref),
                    error=str(exc)
                )

    def _wait_for_mode(self, ref, element, wait_for: str | None, timeout_ms: int) -> None:
        if not wait_for:
            return

        mode = str(wait_for).strip().lower()
        if mode == "present":
            return

        if mode == "visible":
            if element.is_displayed():
                return

            timeout_sec = max(0.0, float(timeout_ms) / 1000.0)
            deadline = time.monotonic() + timeout_sec
            while time.monotonic() < deadline:
                time.sleep(0.05)
                refreshed = self._find_element(ref)
                if refreshed.is_displayed():
                    return

            raise TimeoutError("Element not visible")

        raise ValueError(f"Unsupported wait_for mode for Appium: {wait_for}")

    def _execute_action(self, plan: ActionPlan, element) -> None:
        if plan.action_type in ("tap", "click"):
            element.click()

        elif plan.action_type == "type":
            value = plan.input_value or ""
            element.clear()
            element.send_keys(value)

        elif plan.action_type == "scroll":
            self._scroll_to_element(element)

        elif plan.action_type == "swipe":
            direction = (plan.input_value or "up").lower()
            self._swipe_from_element(element, direction)

        elif plan.action_type == "long_press":
            self._long_press(element, plan)

        elif plan.action_type == "double_tap":
            self._double_tap(element)

        elif plan.action_type == "pinch":
            self._pinch(element, zoom_in=False)

        elif plan.action_type == "zoom":
            self._pinch(element, zoom_in=True)

        elif plan.action_type == "drag":
            self._drag(element, plan)

        else:
            logger.warning(
                "AppiumAdapter.execute: unsupported action_type=%s — no-op",
                plan.action_type,
            )

    async def validate(self, plan: ValidationPlan) -> ValidationResult:
        """
        Assert expected mobile screen state.

        assertion_type values:
          "text_visible"  — page_source contains expected_value text
          "element_state" — XPath element exists and is displayed
          "activity"      — current_activity contains expected_value fragment
        """
        t0 = time.monotonic()

        wiring_plan = self._prepare_webview_switch_metadata_for_operation(
            operation_type="validate",
            instruction=plan.expected_value,
            target_metadata=self._webview_validate_metadata if isinstance(getattr(self, "_webview_validate_metadata", None), dict) else None,
            config=getattr(self, "_config", None),
        )
        logger.debug("AppiumAdapter.validate webview switch wiring plan: %s", wiring_plan)

        try:
            passed, actual = self._run_assertion_with_optional_fake_webview_switch(plan, wiring_plan)
            duration_ms = int((time.monotonic() - t0) * 1000)
            return ValidationResult(passed=passed, actual_value=actual, duration_ms=duration_ms)
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("AppiumAdapter.validate failed: %s", exc)
            return ValidationResult(
                passed=False,
                actual_value=str(exc),
                duration_ms=duration_ms,
            )

    async def screenshot(self) -> ArtifactRef:
        """
        Capture a screenshot and save it to artifacts/<timestamp>.png.
        """
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc)
        filename = f"step_{ts.strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = _ARTIFACTS_DIR / filename

        png_bytes: bytes = self._driver.get_screenshot_as_png()
        path.write_bytes(png_bytes)

        logger.debug("AppiumAdapter.screenshot saved: %s", path)
        return ArtifactRef(
            type="screenshot",
            path=str(path),
            timestamp=ts.isoformat(),
        )

    async def extract_text(self, ref, timeout_ms: int = 5000) -> str:
        """
        Extract user-visible text from a resolved mobile element.

        Resolution order:
          1) element.text
          2) element.get_attribute("content-desc")
          3) element.get_attribute("value")
          4) element.get_attribute("text")
          5) element.get_attribute("name")
        """
        del timeout_ms  # reserved for future wait/retry strategy
        target_metadata = ref.get("metadata") if isinstance(ref, dict) else None
        wiring_plan = self._prepare_webview_switch_metadata_for_operation(
            operation_type="extract",
            instruction=None,
            target_metadata=target_metadata if isinstance(target_metadata, dict) else None,
            config=getattr(self, "_config", None),
        )
        logger.debug("AppiumAdapter.extract_text webview switch wiring plan: %s", wiring_plan)

        return self._extract_text_with_optional_fake_webview_switch(ref, wiring_plan)

    def _extract_text_base(self, ref) -> str:
        element = self._find_element(ref)
        text_value = (getattr(element, "text", None) or "").strip()
        if text_value:
            return text_value
        for attr in ("content-desc", "value", "text", "name"):
            try:
                value = (element.get_attribute(attr) or "").strip()
                if value:
                    return value
            except Exception:
                continue
        raise ValueError(f"No extractable text found for ref={ref!r}")

    def _run_assertion_with_optional_fake_webview_switch(self, plan: ValidationPlan, wiring_plan: dict[str, object]) -> tuple[bool, str]:
        execution_args = self._build_real_switch_execution_args("validate", wiring_plan)
        if execution_args is None:
            return self._run_assertion(plan)
        readiness = self._evaluate_webview_readiness_before_switch(operation_type="validate", execution_args=execution_args, wiring_plan=wiring_plan)
        if readiness.get("status") == "failed_closed":
            self._last_webview_switch_execution = {"webview_readiness_diagnostics": readiness}
            return False, "webview_readiness_failed_closed"
        outcome: dict[str, object] = {"value": (False, "validation failed")}

        def _op():
            outcome["value"] = self._webview_validate_operation(plan) if callable(self._webview_validate_operation) else self._run_assertion(plan)

        execution = execute_real_driver_switch_with_ref(operation_callable=_op, **execution_args)
        if execution.get("switch_status") == "switched":
            readiness = self._apply_post_switch_readiness_wait(readiness)
            if readiness.get("status") == "failed_closed":
                execution["switch_status"] = "failed"
                execution["reason"] = "readiness_timeout_after_switch"
                execution["warnings"] = sorted(set(list(execution.get("warnings") or []) + ["readiness_timeout_after_switch"]))
        self._last_webview_switch_execution = {"webview_switch_execution": execution}
        self._last_webview_switch_execution["webview_readiness_diagnostics"] = readiness
        if execution.get("switch_status") == "failed" or execution.get("restore_status") == "failed":
            return False, "webview_switch_safety_failed"
        result = outcome.get("value")
        return result if isinstance(result, tuple) and len(result) == 2 else (False, "validation failed")

    def _extract_text_with_optional_fake_webview_switch(self, ref, wiring_plan: dict[str, object]) -> str:
        execution_args = self._build_real_switch_execution_args("extract", wiring_plan)
        if execution_args is None:
            return self._extract_text_base(ref)
        readiness = self._evaluate_webview_readiness_before_switch(operation_type="extract", execution_args=execution_args, wiring_plan=wiring_plan)
        if isinstance(ref, dict) and isinstance(ref.get("metadata"), dict):
            ref["metadata"]["webview_readiness_diagnostics"] = readiness
        if readiness.get("status") == "failed_closed":
            self._last_webview_switch_execution = {"webview_readiness_diagnostics": readiness}
            return ""
        outcome: dict[str, object] = {"value": ""}

        def _op():
            outcome["value"] = self._webview_extract_operation(ref) if callable(self._webview_extract_operation) else self._extract_text_base(ref)

        execution = execute_real_driver_switch_with_ref(operation_callable=_op, **execution_args)
        if execution.get("switch_status") == "switched":
            readiness = self._apply_post_switch_readiness_wait(readiness)
            if readiness.get("status") == "failed_closed":
                execution["switch_status"] = "failed"
                execution["reason"] = "readiness_timeout_after_switch"
                execution["warnings"] = sorted(set(list(execution.get("warnings") or []) + ["readiness_timeout_after_switch"]))
        self._last_webview_switch_execution = {"webview_switch_execution": execution}
        if isinstance(ref, dict) and isinstance(ref.get("metadata"), dict):
            ref["metadata"]["webview_switch_execution"] = execution
            ref["metadata"]["webview_readiness_diagnostics"] = readiness
        if execution.get("switch_status") == "failed" or execution.get("restore_status") == "failed":
            return ""
        return str(outcome.get("value") or "")

    def _get_webview_readiness_config(self) -> dict[str, object]:
        cfg = getattr(getattr(self, "_config", None), "webview_switching", None)
        enabled = bool(getattr(cfg, "webview_readiness_wait_enabled", False))
        return {
            "enabled": enabled,
            "context_timeout_ms": _safe_ms(getattr(cfg, "webview_context_wait_timeout_ms", 0)),
            "poll_interval_ms": max(100, _safe_ms(getattr(cfg, "webview_context_poll_interval_ms", 250), default=250)),
            "target_wait_timeout_ms": _safe_ms(getattr(cfg, "webview_target_wait_timeout_ms", 0)),
            "max_context_refresh_attempts": max(0, min(_safe_ms(getattr(cfg, "max_context_refresh_attempts", 1), default=1), 3)),
            "fail_closed_on_readiness_timeout": bool(getattr(cfg, "fail_closed_on_readiness_timeout", True)),
        }

    def _evaluate_webview_readiness_before_switch(self, *, operation_type: str, execution_args: dict[str, object], wiring_plan: dict[str, object]) -> dict[str, object]:
        ready_cfg = self._get_webview_readiness_config()
        if not ready_cfg["enabled"]:
            return build_webview_readiness_plan(enabled=False, operation_type=operation_type)
        context_timeout_ms = int(ready_cfg["context_timeout_ms"])
        poll_ms = int(ready_cfg["poll_interval_ms"])
        attempts = int(ready_cfg["max_context_refresh_attempts"])
        start = time.monotonic()
        refresh_attempts = 0
        context_ref = execution_args.get("context_ref")
        context_ok = bool(getattr(context_ref, "safe_metadata", {}).get("internal_context_ref_available"))
        while (not context_ok) and refresh_attempts < attempts and ((time.monotonic() - start) * 1000) < context_timeout_ms:
            refresh_attempts += 1
            context_inventory = self._collect_real_context_inventory_for_switch()
            plan = wiring_plan.get("webview_switch_wiring_plan") if isinstance(wiring_plan, dict) else {}
            context_ref = resolve_real_webview_context_ref(
                context_inventory=context_inventory,
                selected_context_index=plan.get("selected_context_index") if isinstance(plan, dict) and isinstance(plan.get("selected_context_index"), int) else None,
                selected_context_type=str(plan.get("selected_context_type") if isinstance(plan, dict) else ""),
            )
            context_ok = bool(getattr(context_ref, "safe_metadata", {}).get("internal_context_ref_available"))
            if context_ok:
                execution_args["context_ref"] = context_ref
                break
            time.sleep(poll_ms / 1000.0)
        plan = build_webview_readiness_plan(
            enabled=True,
            operation_type=operation_type,
            timeout_ms=context_timeout_ms,
            poll_interval_ms=poll_ms,
            max_context_refresh_attempts=attempts,
        )
        plan["context_refresh_attempts"] = refresh_attempts
        if not context_ok and bool(ready_cfg["fail_closed_on_readiness_timeout"]):
            plan["status"] = "failed_closed"
            plan["reason"] = "readiness_timeout_before_switch"
            plan["warnings"] = sorted(set(list(plan.get("warnings") or []) + ["safe_failed_closed"]))
        return plan

    def _apply_post_switch_readiness_wait(self, readiness: dict[str, object]) -> dict[str, object]:
        cfg = self._get_webview_readiness_config()
        timeout_ms = int(cfg["target_wait_timeout_ms"])
        if timeout_ms <= 0:
            return readiness
        readiness["target_wait_attempted"] = True
        time.sleep(timeout_ms / 1000.0)
        if bool(cfg["fail_closed_on_readiness_timeout"]):
            readiness["status"] = "failed_closed"
            readiness["reason"] = "readiness_timeout_after_switch"
            readiness["warnings"] = sorted(set(list(readiness.get("warnings") or []) + ["safe_failed_closed"]))
        return readiness

    def _build_real_switch_execution_args(self, operation_type: str, wiring_plan: dict[str, object]) -> dict[str, object] | None:
        if operation_type not in {"validate", "extract"}:
            return None
        plan = wiring_plan.get("webview_switch_wiring_plan") if isinstance(wiring_plan, dict) else None
        if not isinstance(plan, dict) or not plan.get("switch_ready"):
            return None
        if not bool(plan.get("fail_closed_on_restore_failure")):
            return None
        context_inventory = self._collect_real_context_inventory_for_switch()
        context_map = build_real_webview_context_map(context_inventory=context_inventory)
        readiness_cfg = self._get_webview_readiness_config()
        if not bool(context_map.get("context_map_available")) and not bool(readiness_cfg.get("enabled")):
            return None
        selected_context_index = plan.get("selected_context_index")
        selected_context_type = plan.get("selected_context_type")
        context_ref = resolve_real_webview_context_ref(
            context_inventory=context_inventory,
            selected_context_index=selected_context_index if isinstance(selected_context_index, int) else None,
            selected_context_type=str(selected_context_type or ""),
        )
        if not bool(context_ref.safe_metadata.get("internal_context_ref_available")) and not bool(readiness_cfg.get("enabled")):
            return None
        return {
            "context_ref": context_ref,
            "explicit_opt_in": True,
            "get_current_context": self._webview_get_current_context_callable(),
            "switch_context": self._webview_switch_context_callable(),
            "restore_context": self._webview_restore_context_callable(),
        }

    def _build_fake_switch_execution_args(self, operation_type: str, wiring_plan: dict[str, object]) -> dict[str, object] | None:
        return self._build_real_switch_execution_args(operation_type, wiring_plan)

    def _collect_real_context_inventory_for_switch(self) -> dict[str, object]:
        try:
            contexts = self._driver.contexts
            if isinstance(contexts, (list, tuple, set)):
                return {"contexts": [str(v) for v in contexts]}
            if contexts is not None:
                return {"contexts": [str(contexts)]}
        except Exception:
            return {"contexts": []}
        return {"contexts": []}

    def _webview_get_current_context_callable(self):
        def _get():
            if callable(self._webview_get_current_context):
                return self._webview_get_current_context()
            return self._driver.current_context
        return _get

    def _webview_switch_context_callable(self):
        def _switch(raw_name: str):
            if callable(self._webview_switch_context):
                self._webview_switch_context(raw_name)
                return
            self._driver.switch_to.context(raw_name)
        return _switch

    def _webview_restore_context_callable(self):
        def _restore(original_context: str | None):
            if original_context is None:
                raise RuntimeError("original_context_missing")
            if callable(self._webview_restore_context):
                self._webview_restore_context(original_context)
                return
            self._driver.switch_to.context(original_context)
        return _restore


    def _prepare_webview_switch_metadata_for_operation(
        self,
        *,
        operation_type: str,
        instruction: str | None,
        target_metadata: dict | None,
        config,
    ) -> dict[str, object]:
        del instruction
        metadata = target_metadata if isinstance(target_metadata, dict) else {}
        eligibility = metadata.get("webview_switch_eligibility") if isinstance(metadata.get("webview_switch_eligibility"), dict) else None
        selection = metadata.get("webview_context_selection") if isinstance(metadata.get("webview_context_selection"), dict) else None

        out: dict[str, object] = {
            "enabled": False,
            "mode": "unknown",
            "operation_type": str(operation_type or "unknown").strip().lower() or "unknown",
            "eligibility_decision": "unknown",
            "context_selection_decision": "unknown",
            "switch_ready": False,
            "reason": "unknown",
            "safe_metadata_only": True,
            "selected_context_type": "unknown",
            "selected_context_index": None,
            "fail_closed_on_restore_failure": False,
        }

        if config is None:
            out["reason"] = "disabled_by_config"
            return {"webview_switch_wiring_plan": out}

        config_operation_type = "verify" if out["operation_type"] == "validate" else out["operation_type"]
        switch_cfg = is_webview_switching_enabled_for_operation(config=config, operation_type=config_operation_type)
        out["enabled"] = bool(switch_cfg.get("enabled"))
        out["mode"] = str(switch_cfg.get("mode") or "unknown")
        out["reason"] = _safe_wiring_reason(switch_cfg.get("reason"))

        if not out["enabled"]:
            return {"webview_switch_wiring_plan": out}

        eligibility_decision = str((eligibility or {}).get("decision") or "unknown").strip().lower()
        if eligibility_decision not in {"allowed", "blocked", "deferred", "unknown"}:
            eligibility_decision = "unknown"
        out["eligibility_decision"] = eligibility_decision

        if eligibility is None:
            out["reason"] = "missing_eligibility"
            return {"webview_switch_wiring_plan": out}
        if eligibility_decision != "allowed":
            out["reason"] = "eligibility_not_allowed"
            return {"webview_switch_wiring_plan": out}

        selection_decision = str((selection or {}).get("decision") or "unknown").strip().lower()
        if selection_decision not in {"selected", "blocked", "deferred", "unknown"}:
            selection_decision = "unknown"
        out["context_selection_decision"] = selection_decision

        if selection is None:
            out["reason"] = "missing_context_selection"
            return {"webview_switch_wiring_plan": out}
        if selection_decision != "selected":
            out["reason"] = "context_not_selected"
            return {"webview_switch_wiring_plan": out}

        selected_context_type = _sanitize_context_type((selection or {}).get("selected_context_type"))
        out["selected_context_type"] = "webview" if selected_context_type in {"webview", "webview/chromium"} else selected_context_type
        out["selected_context_index"] = (selection or {}).get("selected_context_index") if isinstance((selection or {}).get("selected_context_index"), int) else None
        out["fail_closed_on_restore_failure"] = True
        if selected_context_type not in {"webview", "webview/chromium"}:
            out["reason"] = "selected_context_type_not_webview"
            return {"webview_switch_wiring_plan": out}
        if out["selected_context_index"] is None:
            out["reason"] = "context_not_selected"
            return {"webview_switch_wiring_plan": out}

        out["switch_ready"] = True
        out["reason"] = "switch_ready"
        return {"webview_switch_wiring_plan": out}



    def execute_system_dialog_action(
        self,
        *,
        requested_action: str,
        hierarchy_xml: str | None = None,
        system_dialog_detection: dict | None = None,
        system_dialog_guardrails: dict | None = None,
        explicit_opt_in: bool = False,
    ) -> dict[str, object]:
        xml = hierarchy_xml
        if xml is None:
            try:
                xml = self._driver.page_source
            except Exception:
                xml = None

        detection = system_dialog_detection
        if not isinstance(detection, dict):
            detection = detect_system_dialog(
                platform=self.platform,
                capabilities=self._safe_capabilities(),
                app_state={},
                hierarchy_xml=xml,
            )

        guardrails = system_dialog_guardrails
        if not isinstance(guardrails, dict):
            guardrails = evaluate_system_dialog_guardrails(
                system_dialog_detection=detection,
                requested_action=requested_action,
                explicit_opt_in=explicit_opt_in,
            )

        candidate = resolve_system_dialog_action_candidate(
            hierarchy_xml=xml,
            system_dialog_detection=detection,
            system_dialog_guardrails=guardrails,
            requested_action=requested_action,
            explicit_opt_in=explicit_opt_in,
        )
        return execute_system_dialog_action(driver=self._driver, candidate=candidate, explicit_opt_in=explicit_opt_in)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_activity(self) -> str:
        """Return the current Android activity or a stable iOS fallback."""
        try:
            return self._driver.current_activity or "unknown_activity"
        except Exception:
            pass
        # iOS / fallback: use the app bundle id if available
        try:
            caps = self._driver.capabilities or {}
            return caps.get("bundleId") or caps.get("appPackage") or "unknown_app"
        except Exception:
            return "unknown_app"

    def _find_element(self, ref):
        """
        Locate an element using the ref produced by AppiumHierarchyResolver.

        Supported ref formats:
          JSON string: '{"by": "xpath", "value": "//android.widget.Button[@text='Login']"}'
          dict:        {"by": "xpath", "value": "//android.widget.Button[@text='Login']"}
          raw XPath:   "//android.widget.Button[@text='Login']"  (legacy)
        """
        # Decode JSON string refs from AppiumHierarchyResolver
        if isinstance(ref, str):
            try:
                ref = json.loads(ref)
            except (json.JSONDecodeError, ValueError):
                pass  # treat as raw XPath string
        # Import AppiumBy lazily — keeps the package installable without appium client
        try:
            from appium.webdriver.common.appiumby import AppiumBy  # type: ignore
            BY_MAP = {
                "xpath":            AppiumBy.XPATH,
                "id":               AppiumBy.ID,
                "accessibility id": AppiumBy.ACCESSIBILITY_ID,
                "class name":       AppiumBy.CLASS_NAME,
                "name":             AppiumBy.ACCESSIBILITY_ID,  # alias
            }
        except ImportError:
            try:
                # Fallback: use Selenium By strings directly
                from selenium.webdriver.common.by import By  # type: ignore
                BY_MAP = {
                    "xpath":            By.XPATH,
                    "id":               By.ID,
                    "class name":       By.CLASS_NAME,
                }
            except ImportError:
                # Neither appium-python-client nor selenium installed —
                # use raw string constants (the MagicMock driver accepts any value)
                BY_MAP = {
                    "xpath":            "xpath",
                    "id":               "id",
                    "accessibility id": "accessibility id",
                    "class name":       "class name",
                }

        if isinstance(ref, dict):
            by_key = str(ref.get("by", "xpath")).lower()
            value  = ref.get("value", "")
            by     = BY_MAP.get(by_key, by_key)   # pass-through unknown by values
            return self._driver.find_element(by, value)

        # Raw XPath string fallback
        try:
            by_xpath = BY_MAP.get("xpath")
        except Exception:
            by_xpath = "xpath"
        return self._driver.find_element(by_xpath, str(ref))

    def _scroll_to_element(self, element) -> None:
        """
        Scroll element into view using Appium W3C Actions.
        Gracefully degrades if the driver does not support the action.
        """
        try:
            self._driver.execute_script("mobile: scrollGesture", {
                "elementId": element.id,
                "direction": "down",
                "percent": 0.5,
            })
        except Exception:
            try:
                # Fallback: just send a no-op scroll via touch
                location = element.location
                self._driver.execute_script(
                    "arguments[0].scrollIntoView(true);", element
                )
            except Exception as exc:
                logger.warning("scroll_to_element fallback failed: %s", exc)

    def _swipe_from_element(self, element, direction: str) -> None:
        """
        Execute a swipe gesture starting from element's centre.
        direction: "up" | "down" | "left" | "right"
        """
        try:
            location = element.location
            size = element.size
            start_x = location["x"] + size["width"] // 2
            start_y = location["y"] + size["height"] // 2

            offsets = {
                "up":    (0, -300),
                "down":  (0,  300),
                "left":  (-300, 0),
                "right": (300,  0),
            }
            dx, dy = offsets.get(direction, (0, -300))
            end_x = max(0, start_x + dx)
            end_y = max(0, start_y + dy)

            self._driver.swipe(start_x, start_y, end_x, end_y, duration=500)
        except Exception as exc:
            logger.warning("swipe_from_element failed direction=%s: %s", direction, exc)

    # ------------------------------------------------------------------
    # Mobile gesture vocabulary (M1)
    # ------------------------------------------------------------------

    def _is_ios(self) -> bool:
        return str(self.platform).lower().startswith("ios")

    def _gesture_duration_ms(self, plan: ActionPlan, default_ms: int) -> int:
        """Optional duration override via a numeric input_value (milliseconds)."""
        try:
            value = int(str(plan.input_value).strip())
            return value if value > 0 else default_ms
        except (TypeError, ValueError):
            return default_ms

    def _long_press(self, element, plan: ActionPlan) -> None:
        """Press and hold an element to open its context menu.

        Android → ``mobile: longClickGesture`` (duration in ms); iOS →
        ``mobile: touchAndHold`` (duration in seconds). Default hold ≈ 1 s.
        """
        duration_ms = self._gesture_duration_ms(plan, _LONG_PRESS_DEFAULT_MS)
        if self._is_ios():
            self._driver.execute_script(
                "mobile: touchAndHold", {"elementId": element.id, "duration": duration_ms / 1000.0}
            )
        else:
            self._driver.execute_script(
                "mobile: longClickGesture", {"elementId": element.id, "duration": duration_ms}
            )

    def _double_tap(self, element) -> None:
        """Double-tap an element. Android → ``mobile: doubleClickGesture``;
        iOS → ``mobile: doubleTap``."""
        if self._is_ios():
            self._driver.execute_script("mobile: doubleTap", {"elementId": element.id})
        else:
            self._driver.execute_script("mobile: doubleClickGesture", {"elementId": element.id})

    def _pinch(self, element, *, zoom_in: bool) -> None:
        """Pinch-to-zoom on an element.

        ``zoom_in`` True spreads (zoom in), False pinches closed (zoom out).
        Android → ``mobile: pinchOpenGesture`` / ``pinchCloseGesture`` (percent);
        iOS → ``mobile: pinch`` (scale >1 to zoom in, <1 to zoom out).
        """
        if self._is_ios():
            scale = 2.0 if zoom_in else 0.5
            self._driver.execute_script(
                "mobile: pinch", {"elementId": element.id, "scale": scale, "velocity": 1.0}
            )
        else:
            name = "mobile: pinchOpenGesture" if zoom_in else "mobile: pinchCloseGesture"
            self._driver.execute_script(name, {"elementId": element.id, "percent": 0.75})

    def _drag(self, element, plan: ActionPlan) -> None:
        """Drag an element by a directional offset from its centre.

        Direction comes from ``input_value`` (up/down/left/right, default up).
        Android → ``mobile: dragGesture`` (elementId + endX/endY); iOS →
        ``mobile: dragFromToForDuration`` (from/to coordinates).
        """
        location = element.location
        size = element.size
        start_x = location["x"] + size["width"] // 2
        start_y = location["y"] + size["height"] // 2

        direction = (plan.input_value or "up").lower()
        offsets = {"up": (0, -300), "down": (0, 300), "left": (-300, 0), "right": (300, 0)}
        dx, dy = offsets.get(direction, (0, -300))
        end_x = max(0, start_x + dx)
        end_y = max(0, start_y + dy)

        if self._is_ios():
            self._driver.execute_script(
                "mobile: dragFromToForDuration",
                {"duration": 1.0, "fromX": start_x, "fromY": start_y, "toX": end_x, "toY": end_y},
            )
        else:
            self._driver.execute_script(
                "mobile: dragGesture",
                {"elementId": element.id, "endX": end_x, "endY": end_y},
            )

    def _run_assertion(self, plan: ValidationPlan) -> tuple[bool, str]:
        """Run the appropriate Appium assertion. Returns (passed, actual_value)."""
        expected = plan.expected_value or ""

        if plan.assertion_type == "text_visible":
            try:
                source = self._driver.page_source
                return (expected.lower() in source.lower(), source[:200])
            except Exception as exc:
                return (False, str(exc))

        elif plan.assertion_type == "element_state":
            # expected is an XPath expression
            try:
                from appium.webdriver.common.appiumby import AppiumBy  # type: ignore
                by = AppiumBy.XPATH
            except ImportError:
                try:
                    from selenium.webdriver.common.by import By  # type: ignore
                    by = By.XPATH
                except ImportError:
                    by = "xpath"
            try:
                elements = self._driver.find_elements(by, expected)
                if elements and elements[0].is_displayed():
                    return (True, "visible")
                return (False, "not visible")
            except Exception as exc:
                return (False, str(exc))

        elif plan.assertion_type == "activity":
            activity = self._get_activity()
            return (expected.lower() in activity.lower(), activity)

        else:
            logger.warning("AppiumAdapter: unknown assertion_type=%s", plan.assertion_type)
            return (False, f"unknown assertion_type: {plan.assertion_type}")
