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
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from bubblegum.core import sdk
from bubblegum.core.schemas import StepResult
from bubblegum.core.scope import ScopeStack, SessionScope, close_dialog_web

logger = logging.getLogger(__name__)


_LABEL_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Extracts the name component of a role=<role>[name="<name>"] ref (kept in
# sync with the Playwright adapter's ref grammar).
_REF_NAME_RE = re.compile(r'\[name="([^"]+)"\]')


def _sanitize_label(label: str) -> str:
    """Make a label safe for use as a filename fragment."""
    cleaned = _LABEL_SANITIZE_RE.sub("_", label).strip("_")
    return cleaned or "bubblegum"


class BubblegumProbeError(RuntimeError):
    """Raised when a state probe (``is_checked`` etc.) cannot resolve its target."""


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
        # 22E-3: optional label used to name auto-screenshots on failure.
        # The pytest fixture sets this from request.node.nodeid; tests that
        # construct a session directly can set it themselves.
        self._label: str | None = None
        self._artifacts_dir: Path = Path("artifacts")
        self._failure_screenshots: list[Path] = []
        # Soft assertions (W3): when a verify is soft, a failure is recorded
        # but never surfaces until assert_all_passed() aggregates them. The
        # default is flipped on inside a `with s.soft_assertions():` block.
        self._soft_default: bool = False
        self._soft_ids: set[int] = set()

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

    @property
    def label(self) -> str | None:
        """Optional label used to name auto-screenshots and trace artifacts."""
        return self._label

    @label.setter
    def label(self, value: str | None) -> None:
        self._label = value

    @property
    def artifacts_dir(self) -> Path:
        """Directory where auto-screenshots and other artifacts are written."""
        return self._artifacts_dir

    @artifacts_dir.setter
    def artifacts_dir(self, value: Path | str) -> None:
        self._artifacts_dir = Path(value)

    @property
    def failure_screenshots(self) -> list[Path]:
        """Paths of auto-screenshots captured for failed steps in this session."""
        return list(self._failure_screenshots)

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
        await self._maybe_screenshot_on_failure(result)
        return result

    async def verify(self, instruction: str, *, soft: bool | None = None, **kwargs) -> StepResult:
        """Assert an expected state in natural language.

        By default a failing ``verify`` is recorded in the session results and
        surfaced together at :meth:`assert_all_passed` — it does not raise on
        the spot. Pass ``soft=True`` (or run inside ``with
        s.soft_assertions():``) to explicitly mark the failure as soft; the
        failed StepResult is tagged ``target.metadata["soft"] = True`` so
        reports can distinguish soft expectations from hard ones.
        """
        effective_soft = self._soft_default if soft is None else soft
        result = await sdk.verify(
            instruction,
            channel=self._channel,
            page=self._page,
            driver=self._driver,
            **self._merged(kwargs),
        )
        if effective_soft and result.status == "failed":
            self._mark_soft(result)
        self._results.append(result)
        self._log(instruction, result)
        await self._maybe_screenshot_on_failure(result)
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
        await self._maybe_screenshot_on_failure(result)
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
        await self._maybe_screenshot_on_failure(result)
        return result

    # ------------------------------------------------------------------
    # Navigation (Phase 22E-7) — web only
    # ------------------------------------------------------------------

    async def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> None:
        """Navigate the wrapped Playwright page and wait for the load state.

        Web-only convenience so tests don't reach into ``session.page``:

            await s.goto(f"{widget_lab}/radios.html")
            await s.act("Click Red radio")
        """
        if self._channel != "web" or self._page is None:
            raise NotImplementedError("goto() is only available on web sessions")
        await self._page.goto(url, wait_until=wait_until)

    # ------------------------------------------------------------------
    # State probes (Phase 22E-3) — web only
    # ------------------------------------------------------------------

    async def is_checked(self, target: str, **kwargs) -> bool:
        """Return whether the NL-resolved checkbox/radio is checked.

        Example: ``await s.is_checked("Newsletter")``.
        Raises ``BubblegumProbeError`` when the target cannot be resolved.
        """
        locator = await self._resolve_probe_locator(target, **kwargs)
        return bool(await locator.first.is_checked())

    async def selected_value(self, target: str, **kwargs) -> str:
        """Return the current value of the NL-resolved <select> / combobox.

        Reads ``input_value()`` so it works for native ``<select>`` and
        ``<input>``; ARIA comboboxes that expose their value as text need a
        custom probe (extract on the trigger).
        """
        locator = await self._resolve_probe_locator(target, **kwargs)
        return await locator.first.input_value()

    async def is_visible(self, target: str, **kwargs) -> bool:
        """Return whether the NL-resolved element is visible to the user."""
        locator = await self._resolve_probe_locator(target, **kwargs)
        return bool(await locator.first.is_visible())

    async def _resolve_probe_locator(self, target: str, **kwargs):
        """Resolve an NL target via grounding and return a Playwright Locator.

        Uses ``sdk.act`` with ``action_type="verify"`` + ``dry_run=True`` so
        the resolver chain runs but the adapter never executes anything. The
        resulting ``target.ref`` is handed back to the adapter's existing
        ref-to-locator helper.
        """
        if self._channel != "web":
            raise NotImplementedError(
                "Bubblegum state probes are web-only in Phase 22E-3"
            )

        merged = self._merged(kwargs)
        merged["dry_run"] = True
        merged.setdefault("action_type", "verify")

        result = await sdk.act(
            target,
            channel="web",
            page=self._page,
            driver=self._driver,
            **merged,
        )
        if result.target is None:
            err = result.error.message if result.error else "no candidates"
            raise BubblegumProbeError(
                f"Could not resolve {target!r} for state probe: {err}"
            )

        adapter = sdk._get_adapter("web", page=self._page)
        ref = result.target.ref
        locator = adapter._resolve_locator(ref)

        # 22E-9 fix: roles like paragraph / status / generic expose their
        # text as snapshot *content*, not as an accessible name, so a
        # role=...[name="..."] ref built from the snapshot can match zero
        # elements (and Playwright's is_visible() reports False for zero
        # matches instead of raising). When the role locator matches
        # nothing, fall back to an exact text match on the same string.
        try:
            if await locator.count() > 0:
                return locator
        except Exception:
            return locator

        name_match = _REF_NAME_RE.search(ref)
        if name_match:
            return self._page.get_by_text(name_match.group(1), exact=True)
        return locator

    # ------------------------------------------------------------------
    # Auto-screenshot on failure (Phase 22E-3)
    # ------------------------------------------------------------------

    async def _maybe_screenshot_on_failure(self, result: StepResult) -> None:
        """Capture a screenshot when a step fails.

        Path format: ``<artifacts_dir>/<label>-step<N>.png`` where ``<label>``
        is the session label (pytest fixture sets it from the test nodeid)
        and ``N`` is 1-based step index. No-op for non-web channels, sessions
        without a page, dry-run results, or when label is unset.
        """
        if result.status != "failed":
            return
        if self._channel != "web" or self._page is None:
            return
        if not self._label:
            return

        try:
            self._artifacts_dir.mkdir(parents=True, exist_ok=True)
            step_idx = len(self._results)
            safe_label = _sanitize_label(self._label)
            path = self._artifacts_dir / f"{safe_label}-step{step_idx}.png"
            await self._page.screenshot(path=str(path))
            self._failure_screenshots.append(path)
            logger.debug("Auto-screenshot on failure: %s", path)
        except Exception as exc:
            logger.warning("Auto-screenshot capture failed: %s", exc)

    async def capture_failure_screenshot(self, suffix: str = "final") -> Path | None:
        """Capture a screenshot now (used by the pytest fixture finalizer).

        Returns the path of the written file, or None if capture is skipped
        (no page/driver / no label / IO error). Works for both web (via the
        Playwright page) and mobile (via the Appium driver).
        """
        handle = self._page if self._channel == "web" else self._driver
        if handle is None or not self._label:
            return None
        try:
            self._artifacts_dir.mkdir(parents=True, exist_ok=True)
            step_idx = len(self._results) + 1
            safe_label = _sanitize_label(self._label)
            tag = suffix if suffix == "final" else f"step{step_idx}"
            path = self._artifacts_dir / f"{safe_label}-{tag}.png"
            if self._channel == "web":
                await self._page.screenshot(path=str(path))
            else:
                # Appium's get_screenshot_as_png() is synchronous.
                png = self._driver.get_screenshot_as_png()
                path.write_bytes(png)
            self._failure_screenshots.append(path)
            return path
        except Exception as exc:
            logger.warning("Auto-screenshot capture failed: %s", exc)
            return None

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

    @contextmanager
    def soft_assertions(self) -> Iterator["BubblegumSession"]:
        """Treat every ``verify`` inside the block as a soft assertion.

        Soft failures are collected rather than surfaced one at a time, so a
        single run reports *all* failing expectations instead of stopping at
        the first. Call :meth:`assert_all_passed` afterwards to raise an
        aggregated error:

            with s.soft_assertions():
                await s.verify("Total is $42")
                await s.verify("Cart shows 3 items")
                await s.verify("Discount applied")
            s.assert_all_passed()   # raises listing every failure

        Re-entrant: the prior default is restored on exit.
        """
        previous = self._soft_default
        self._soft_default = True
        try:
            yield self
        finally:
            self._soft_default = previous

    def _mark_soft(self, result: StepResult) -> None:
        """Tag a failed StepResult as a soft assertion failure.

        Records the result identity for :meth:`assert_all_passed` messaging and
        sets ``target.metadata["soft"] = True`` when a target is present so the
        flag flows into JSON/HTML/JUnit reports.
        """
        self._soft_ids.add(id(result))
        if result.target is not None and isinstance(result.target.metadata, dict):
            result.target.metadata["soft"] = True

    def soft_failures(self) -> list[StepResult]:
        """All failed steps recorded as soft assertions in this session."""
        return [r for r in self._results if id(r) in self._soft_ids and r.status == "failed"]

    def assert_all_passed(self) -> None:
        """Raise AssertionError if any step has status 'failed'.

        Aggregates every failure — hard and soft alike — into one error so a
        soft-assertion run surfaces all problems at once. Recovered and dry_run
        steps are not considered failures.
        """
        failures = [r for r in self._results if r.status == "failed"]
        if not failures:
            return
        soft_count = sum(1 for r in failures if id(r) in self._soft_ids)
        msgs = []
        for i, r in enumerate(failures):
            tag = " [soft]" if id(r) in self._soft_ids else ""
            detail = r.error.message if r.error else "failed"
            msgs.append(f"  [{i+1}]{tag} {r.action!r}: {detail}")
        header = f"{len(failures)} step(s) failed"
        if soft_count:
            header += f" ({soft_count} soft)"
        raise AssertionError(f"{header}:\n" + "\n".join(msgs))

    async def explain(self, instruction: str, *, print_output: bool = True, **kwargs) -> str:
        """Explain how a step resolves — ranked candidates, per-signal scores,
        the tier it stops at, and why the winner won.

        Runs a dry-run resolution (no execution; nothing is appended to the
        session results) and renders the decision from the captured traces.
        Returns the explanation string and, by default, prints it:

            await s.explain("Click Login")
        """
        from bubblegum.reporting.explain import format_explanation

        merged = self._merged(kwargs)
        merged["dry_run"] = True
        result = await sdk.act(
            instruction,
            channel=self._channel,
            page=self._page,
            driver=self._driver,
            **merged,
        )
        text = format_explanation(result)
        if print_output:
            print(text)
        return text

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
