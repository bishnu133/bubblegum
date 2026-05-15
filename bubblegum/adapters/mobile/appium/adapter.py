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

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import json

from bubblegum.adapters.base import BaseAdapter
from bubblegum.core.memory.fingerprint import compute_signature
from bubblegum.core.mobile.framework_detector import detect_mobile_surface
from bubblegum.core.mobile.system_dialog import detect_system_dialog
from bubblegum.core.mobile.webview_diagnostics import build_webview_switch_diagnostics
from bubblegum.core.mobile.webview_guardrails import evaluate_webview_switch_guardrails
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

    # ------------------------------------------------------------------
    # BaseAdapter implementation
    # ------------------------------------------------------------------

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

        try:
            passed, actual = self._run_assertion(plan)
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
