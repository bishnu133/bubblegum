"""
bubblegum/adapters/web/playwright/sync_adapter.py
===================================================
SyncPlaywrightAdapter — synchronous wrapper around the same logic as PlaywrightAdapter.

Used exclusively in integration tests where pytest-playwright provides a synchronous
`page` fixture (playwright.sync_api.Page). This avoids all event loop conflicts between
pytest-asyncio (mode=AUTO) and pytest-playwright.

The async PlaywrightAdapter remains the production adapter — users running Bubblegum
in their async test suites use that. This sync adapter is a test-only convenience.

Phase 1A — integration test support.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

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
_NAME_RE = re.compile(r'\[name="([^"]+)"\]')


class SyncPlaywrightAdapter:
    """
    Synchronous Playwright adapter for integration tests.

    Accepts a playwright.sync_api.Page object (the fixture pytest-playwright provides).
    All methods are plain def — no async/await — so they work inside any event loop context.
    """

    def __init__(self, page) -> None:
        self._page = page

    def collect_context(self, request: ContextRequest) -> UIContext:
        a11y_snapshot: str | None = None
        screenshot: bytes | None = None

        try:
            if request.include_accessibility:
                a11y_snapshot = self._page.locator("body").aria_snapshot()
        except Exception as exc:
            logger.warning("aria_snapshot() failed: %s", exc)

        try:
            if request.include_screenshot:
                screenshot = self._page.screenshot(type="png")
        except Exception as exc:
            logger.warning("screenshot() failed: %s", exc)

        url = self._page.url
        sig = f"{url}:{len(a11y_snapshot or '')}"

        return UIContext(
            a11y_snapshot=a11y_snapshot,
            screenshot=screenshot,
            screen_signature=sig,
        )

    def execute(self, plan: ActionPlan, target: ResolvedTarget) -> ExecutionResult:
        t0 = time.monotonic()
        ref = target.ref
        timeout = plan.options.timeout_ms

        try:
            locator = self._resolve_locator(ref)

            if plan.action_type in ("click", "tap"):
                locator.click(timeout=timeout)
            elif plan.action_type == "type":
                locator.fill(plan.input_value or "", timeout=timeout)
            elif plan.action_type == "select":
                locator.select_option(plan.input_value or "", timeout=timeout)
            elif plan.action_type == "scroll":
                locator.scroll_into_view_if_needed(timeout=timeout)

            duration_ms = int((time.monotonic() - t0) * 1000)
            return ExecutionResult(success=True, duration_ms=duration_ms, element_ref=ref)

        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            return ExecutionResult(success=False, duration_ms=duration_ms, element_ref=ref, error=str(exc))

    def validate(self, plan: ValidationPlan) -> ValidationResult:
        t0 = time.monotonic()
        expected = plan.expected_value or ""
        timeout = plan.timeout_ms

        try:
            if plan.assertion_type == "text_visible":
                try:
                    self._page.get_by_text(expected).wait_for(state="visible", timeout=timeout)
                    passed, actual = True, expected
                except Exception:
                    content = self._page.content()
                    passed = expected.lower() in content.lower()
                    actual = content[:200]

            elif plan.assertion_type == "element_state":
                try:
                    self._page.locator(expected).wait_for(state="visible", timeout=timeout)
                    passed, actual = True, "visible"
                except Exception:
                    passed, actual = False, "not visible"

            elif plan.assertion_type == "page_transition":
                url = self._page.url
                passed, actual = expected.lower() in url.lower(), url

            else:
                passed, actual = False, f"unknown assertion_type: {plan.assertion_type}"

        except Exception as exc:
            passed, actual = False, str(exc)

        duration_ms = int((time.monotonic() - t0) * 1000)
        return ValidationResult(passed=passed, actual_value=actual, duration_ms=duration_ms)

    def screenshot(self) -> ArtifactRef:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc)
        filename = f"step_{ts.strftime('%Y%m%d_%H%M%S_%f')}.png"
        path = _ARTIFACTS_DIR / filename
        path.write_bytes(self._page.screenshot(type="png"))
        return ArtifactRef(type="screenshot", path=str(path), timestamp=ts.isoformat())

    def _resolve_locator(self, ref: str):
        if ref.startswith("role="):
            role_part = ref[len("role="):]
            name_match = _NAME_RE.search(role_part)
            role = _NAME_RE.sub("", role_part).strip()
            if name_match:
                return self._page.get_by_role(role, name=name_match.group(1))
            return self._page.get_by_role(role)
        if ref.startswith('text="') and ref.endswith('"'):
            return self._page.get_by_text(ref[6:-1], exact=True)
        if ref.startswith("text="):
            return self._page.get_by_text(ref[5:], exact=True)
        return self._page.locator(ref)
