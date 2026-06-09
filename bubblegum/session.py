"""
bubblegum/session.py
=====================
BubblegumSession — a stateful wrapper that holds channel + page/driver once,
accumulating step results across a test. Eliminates the need to pass
page=page and channel="web" on every act/verify/extract call.

Usage
-----
    # Web
    async with BubblegumSession.web(page) as s:
        await s.act("Click Login")
        await s.act('Enter "tomsmith" into Username')
        await s.verify("Secure Area visible")
        value = await s.extract("Get flash message")
        s.assert_all_passed()

    # Mobile
    async with BubblegumSession.mobile(driver) as s:
        await s.act("Tap Login")

    # Dry-run mode — resolve only, no execution
    async with BubblegumSession.web(page, dry_run=True) as s:
        await s.act("Click Login")
        s.print_plan()

    # Manual (no context manager)
    session = BubblegumSession.web(page)
    await session.act("Click Login")
    print(session.summary())
"""

from __future__ import annotations

import logging
from typing import Any

from bubblegum.core import sdk
from bubblegum.core.schemas import StepResult
from bubblegum.core.scope import ScopeStack, SessionScope, close_dialog_web

logger = logging.getLogger(__name__)


class BubblegumSession:
    """Stateful multi-step session for Bubblegum.

    Holds channel + page/driver so callers don't repeat them on every step.
    Accumulates StepResult objects for summary reporting and assertions.

    Create via class methods rather than directly:
        BubblegumSession.web(page)
        BubblegumSession.mobile(driver)
    """

    def __init__(
        self,
        channel: str,
        page=None,
        driver=None,
        dry_run: bool = False,
        **defaults: Any,
    ) -> None:
        if channel == "web" and page is None:
            raise ValueError("BubblegumSession.web() requires page=")
        if channel == "mobile" and driver is None:
            raise ValueError("BubblegumSession.mobile() requires driver=")

        self._channel = channel
        self._page = page
        self._driver = driver
        self._dry_run = dry_run
        self._defaults = defaults          # forwarded to every SDK call
        self._results: list[StepResult] = []
        self._scope_stack = ScopeStack()

    # ------------------------------------------------------------------
    # Factory class methods
    # ------------------------------------------------------------------

    @classmethod
    def web(cls, page, *, dry_run: bool = False, **kwargs) -> "BubblegumSession":
        """Create a web session wrapping a Playwright Page."""
        return cls(channel="web", page=page, dry_run=dry_run, **kwargs)

    @classmethod
    def mobile(cls, driver, *, dry_run: bool = False, **kwargs) -> "BubblegumSession":
        """Create a mobile session wrapping an Appium WebDriver."""
        return cls(channel="mobile", driver=driver, dry_run=dry_run, **kwargs)

    # ------------------------------------------------------------------
    # Wrapped runtime handles
    # ------------------------------------------------------------------

    @property
    def page(self):
        """The Playwright Page wrapped by a web session (else None)."""
        return self._page

    @property
    def driver(self):
        """The Appium driver wrapped by a mobile session (else None)."""
        return self._driver

    @property
    def channel(self) -> str:
        """The channel name passed at construction (``web`` or ``mobile``)."""
        return self._channel

    # ------------------------------------------------------------------
    # Step methods
    # ------------------------------------------------------------------

    async def act(self, instruction: str, **kwargs) -> StepResult:
        """Execute a natural-language action step."""
        result = await sdk.act(
            instruction,
            channel=self._channel,
            page=self._page,
            driver=self._driver,
            **self._merged(kwargs),
        )
        self._results.append(result)
        self._log(instruction, result)
        return result

    async def verify(self, instruction: str, **kwargs) -> StepResult:
        """Assert an expected state in natural language."""
        result = await sdk.verify(
            instruction,
            channel=self._channel,
            page=self._page,
            driver=self._driver,
            **self._merged(kwargs),
        )
        self._results.append(result)
        self._log(instruction, result)
        return result

    async def extract(self, instruction: str, **kwargs) -> StepResult:
        """Extract text content from a matched element."""
        result = await sdk.extract(
            instruction,
            channel=self._channel,
            page=self._page,
            driver=self._driver,
            **self._merged(kwargs),
        )
        self._results.append(result)
        self._log(instruction, result)
        return result

    async def recover(
        self,
        failed_selector: str,
        intent: str,
        **kwargs,
    ) -> StepResult:
        """Fallback recovery for a stale selector."""
        result = await sdk.recover(
            page=self._page,
            driver=self._driver,
            failed_selector=failed_selector,
            intent=intent,
            channel=self._channel,
            **self._merged(kwargs),
        )
        self._results.append(result)
        self._log(intent, result)
        return result

    # ------------------------------------------------------------------
    # Scope (Phase 22D-6)
    # ------------------------------------------------------------------

    @property
    def current_scope(self) -> SessionScope:
        """The scope frame at the top of the stack (page by default)."""
        return self._scope_stack.current()

    def scope_snapshot(self) -> list[dict]:
        """JSON-safe view of the scope stack for trace artifacts."""
        return self._scope_stack.snapshot()

    def push_scope(
        self,
        type: str,
        *,
        label: str | None = None,
        root_locator=None,
    ) -> SessionScope:
        """Push a new scope frame. Use `close_dialog()` to pop a dialog scope."""
        scope = SessionScope(
            type=type,  # type: ignore[arg-type]
            label=label,
            root_locator=root_locator,
            opened_by=len(self._results),
        )
        return self._scope_stack.push(scope)

    def pop_scope(self) -> SessionScope | None:
        """Pop the top scope frame. No-op when only the base page scope remains."""
        return self._scope_stack.pop()

    async def close_dialog(self) -> dict:
        """Close the active dialog and pop its scope frame.

        Web channel only in 22D-6. Resolution: click an internal close
        affordance (button named close/cancel/dismiss/×/x), otherwise press
        Escape as a fallback. Returns a small report describing how the
        dialog was closed and the resulting scope state.
        """
        if self._channel != "web":
            raise NotImplementedError(
                "close_dialog is only implemented for the web channel in 22D-6"
            )
        report = await close_dialog_web(self._page, self._scope_stack)
        logger.debug("close_dialog: %s", report)
        return report

    # ------------------------------------------------------------------
    # Results & reporting
    # ------------------------------------------------------------------

    def results(self) -> list[StepResult]:
        """All StepResult objects collected so far in this session."""
        return list(self._results)

    def summary(self) -> dict:
        """Return a dict of {total, passed, failed, recovered, dry_run, duration_ms}."""
        counts: dict[str, int] = {"passed": 0, "failed": 0, "recovered": 0, "dry_run": 0, "skipped": 0}
        total_ms = 0
        for r in self._results:
            counts[r.status] = counts.get(r.status, 0) + 1
            total_ms += r.duration_ms
        return {
            "total": len(self._results),
            **counts,
            "duration_ms": total_ms,
        }

    def assert_all_passed(self) -> None:
        """Raise AssertionError if any step has status 'failed'.

        Recovered and dry_run steps are not considered failures.
        """
        failures = [r for r in self._results if r.status == "failed"]
        if not failures:
            return
        msgs = [f"  [{i+1}] {r.action!r}: {r.error.message if r.error else 'failed'}" for i, r in enumerate(failures)]
        raise AssertionError(f"{len(failures)} step(s) failed:\n" + "\n".join(msgs))

    def print_plan(self) -> None:
        """Print a dry-run resolution plan — what each step would act on."""
        print(f"\n── Bubblegum Dry-Run Plan ({len(self._results)} steps) ─────────────")
        for i, r in enumerate(self._results, 1):
            ref = r.target.ref if r.target else "UNRESOLVED"
            resolver = r.target.resolver_name if r.target else "—"
            conf = f"{r.confidence:.2f}" if r.confidence else "—"
            err = f"  ✗ {r.error.message}" if r.error else ""
            print(f"  {i:2}. {r.action!r}")
            print(f"      → {ref}  ({resolver}, conf={conf}){err}")
        print()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "BubblegumSession":
        return self

    async def __aexit__(self, *_) -> None:
        s = self.summary()
        logger.debug(
            "BubblegumSession closed: total=%d passed=%d failed=%d recovered=%d",
            s["total"], s["passed"], s["failed"], s["recovered"],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merged(self, kwargs: dict) -> dict:
        """Merge session defaults with per-call kwargs (call wins on conflict)."""
        merged = dict(self._defaults)
        if self._dry_run and "dry_run" not in kwargs:
            merged["dry_run"] = True
        merged.update(kwargs)
        return merged

    def _log(self, instruction: str, result: StepResult) -> None:
        icon = "✓" if result.status in ("passed", "recovered", "dry_run") else "✗"
        ref = result.target.ref if result.target else "—"
        logger.debug(
            "%s [%s] %r → %s (conf=%.2f)",
            icon, result.status, instruction, ref, result.confidence,
        )
