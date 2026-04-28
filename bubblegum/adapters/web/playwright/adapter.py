"""
bubblegum/adapters/web/playwright/adapter.py
============================================
PlaywrightAdapter — implements BaseAdapter for Playwright (web channel).

collect_context():
  Uses locator("body").aria_snapshot() — NEVER page.accessibility.snapshot() (deprecated).
  Optionally captures screenshot bytes.

execute():
  Dispatches on plan.action_type → click / type / select / scroll.
  Uses target.ref as a Playwright locator string.

validate():
  Supports assertion_type: "text_visible" | "element_state" | "page_transition"

screenshot():
  Saves PNG to artifacts/ (relative to cwd). Returns ArtifactRef.

Phase 1A — fully implemented.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from bubblegum.adapters.base import BaseAdapter
from bubblegum.core.memory.fingerprint import compute_signature
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

_ARTIFACTS_DIR = Path("artifacts")


class PlaywrightAdapter(BaseAdapter):
    """
    Playwright-based adapter for the web channel.

    Args:
        page: A Playwright Page object (sync or async — async assumed here).
    """

    def __init__(self, page) -> None:  # page: playwright.async_api.Page
        self._page = page

    # ------------------------------------------------------------------
    # BaseAdapter implementation
    # ------------------------------------------------------------------

    async def collect_context(self, request: ContextRequest) -> UIContext:
        """
        Capture UIContext from the current Playwright page.

        a11y_snapshot: always collected via locator("body").aria_snapshot()
        screenshot:    collected only when request.include_screenshot is True
        screen_signature: simple hash of page URL + snapshot length
        """
        a11y_snapshot: str | None = None
        screenshot:    bytes | None = None

        try:
            if request.include_accessibility:
                # ✅ Modern API — locator.aria_snapshot() — NOT page.accessibility.snapshot()
                a11y_snapshot = await self._page.locator("body").aria_snapshot()
        except Exception as exc:
            logger.warning("aria_snapshot() failed: %s", exc)

        try:
            if request.include_screenshot:
                screenshot = await self._page.screenshot(type="png")
        except Exception as exc:
            logger.warning("screenshot() failed: %s", exc)

        url = self._page.url
        sig = compute_signature(url, a11y_snapshot)

        return UIContext(
            a11y_snapshot=a11y_snapshot,
            screenshot=screenshot,
            screen_signature=sig,
        )

    async def execute(self, plan: ActionPlan, target: ResolvedTarget) -> ExecutionResult:
        """
        Execute the action against target.ref using Playwright.

        Supported action_types: click, type, select, scroll, tap (alias for click).
        """
        t0 = time.monotonic()
        ref = target.ref
        timeout = plan.options.timeout_ms

        try:
            locator = self._resolve_locator(ref)

            if plan.action_type in ("click", "tap"):
                await locator.click(timeout=timeout)

            elif plan.action_type == "type":
                value = plan.input_value or ""
                await locator.fill(value, timeout=timeout)

            elif plan.action_type == "select":
                value = plan.input_value or ""
                await locator.select_option(value, timeout=timeout)

            elif plan.action_type == "scroll":
                # Scroll the element into view
                await locator.scroll_into_view_if_needed(timeout=timeout)

            else:
                logger.warning(
                    "PlaywrightAdapter.execute: unsupported action_type=%s — no-op",
                    plan.action_type,
                )

            duration_ms = int((time.monotonic() - t0) * 1000)
            return ExecutionResult(
                success=True,
                duration_ms=duration_ms,
                element_ref=ref,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("Execution failed for ref=%r: %s", ref, exc)
            return ExecutionResult(
                success=False,
                duration_ms=duration_ms,
                element_ref=ref,
                error=str(exc),
            )

    async def validate(self, plan: ValidationPlan) -> ValidationResult:
        """
        Assert expected page state.

        assertion_type values:
          "text_visible"     — checks page contains expected_value text
          "element_state"    — checks locator described by expected_value is visible
          "page_transition"  — checks URL contains expected_value fragment
        """
        t0 = time.monotonic()

        try:
            passed, actual = await self._run_assertion(plan)
            duration_ms = int((time.monotonic() - t0) * 1000)
            return ValidationResult(passed=passed, actual_value=actual, duration_ms=duration_ms)
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("Validation failed: %s", exc)
            return ValidationResult(
                passed=False,
                actual_value=str(exc),
                duration_ms=duration_ms,
            )

    async def screenshot(self) -> ArtifactRef:
        """
        Capture a screenshot and save it to artifacts/<timestamp>.png.
        The artifacts/ directory is created relative to cwd if it does not exist.
        """
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc)
        filename = f"step_{ts.strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = _ARTIFACTS_DIR / filename

        png_bytes: bytes = await self._page.screenshot(type="png")
        path.write_bytes(png_bytes)

        logger.debug("Screenshot saved: %s", path)
        return ArtifactRef(
            type="screenshot",
            path=str(path),
            timestamp=ts.isoformat(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_locator(self, ref: str):
        """
        Convert a ref string into a Playwright Locator.

        Supported ref formats:
          role=button[name="Login"]    → page.get_by_role("button", name="Login")
          text="Login"                 → page.get_by_text("Login", exact=True)
          #id / .class / [attr]        → page.locator(ref)  (CSS / XPath pass-through)
          role=button                  → page.get_by_role("button")
        """
        # Semantic role locator: role=<role>[name="<name>"]
        if ref.startswith("role="):
            role_part = ref[len("role="):]
            name_match = _NAME_RE.search(role_part)
            role = _NAME_RE.sub("", role_part).strip()
            if name_match:
                name = name_match.group(1)
                return self._page.get_by_role(role, name=name)
            return self._page.get_by_role(role)

        # Exact text locator: text="Login"
        if ref.startswith('text="') and ref.endswith('"'):
            label = ref[6:-1]
            return self._page.get_by_text(label, exact=True)

        if ref.startswith("text="):
            label = ref[5:]
            return self._page.get_by_text(label, exact=True)

        # CSS / XPath / id pass-through
        return self._page.locator(ref)

    async def _run_assertion(self, plan: ValidationPlan) -> tuple[bool, str]:
        """Run the appropriate Playwright assertion. Returns (passed, actual_value)."""
        expected = plan.expected_value or ""
        timeout  = plan.timeout_ms

        if plan.assertion_type == "text_visible":
            locator = self._page.get_by_text(expected)
            try:
                await locator.wait_for(state="visible", timeout=timeout)
                return (True, expected)
            except Exception:
                content = await self._page.content()
                return (expected.lower() in content.lower(), content[:200])

        elif plan.assertion_type == "element_state":
            locator = self._page.locator(expected)
            try:
                await locator.wait_for(state="visible", timeout=timeout)
                return (True, "visible")
            except Exception:
                return (False, "not visible")

        elif plan.assertion_type == "page_transition":
            url = self._page.url
            return (expected.lower() in url.lower(), url)

        else:
            logger.warning("Unknown assertion_type: %s", plan.assertion_type)
            return (False, f"unknown assertion_type: {plan.assertion_type}")


# ---------------------------------------------------------------------------
# Module-level regex
# ---------------------------------------------------------------------------

import re  # noqa: E402

_NAME_RE = re.compile(r'\[name="([^"]+)"\]')
