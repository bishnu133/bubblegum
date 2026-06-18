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

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from bubblegum.adapters.base import BaseAdapter
from bubblegum.core.coordinates import COORDINATE_CLICK_ACTIONS, normalize_point
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
_TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "not attached",
    "detached",
    "target closed",
    "intercepts pointer events",
    "click intercepted",
    "not visible",
    "not enabled",
)

_MAX_RETRY_CAP = 1
_RETRY_DELAY_SECONDS = 0.05
_WAIT_STATES = {"visible", "attached"}

# Fallback used when ExecutionOptions.nav_wait_ms is unavailable (e.g. an older
# ActionPlan). Bounds how long a non-navigating click waits before concluding
# the click was an in-page action rather than a navigation.
_DEFAULT_NAV_WAIT_MS = 1_000


def _is_transient_execution_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_ERROR_MARKERS)


def _is_strict_mode_violation(exc: Exception) -> bool:
    """True when Playwright refused to act because a locator matched >1 element."""
    return "strict mode violation" in str(exc).lower()


def _retry_budget(retry_count: int | None) -> int:
    if retry_count is None:
        return 0
    return max(0, min(int(retry_count), _MAX_RETRY_CAP))


def _sanitize_retry_reason(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    lower = text.lower()
    if "timeout" in lower or "timed out" in lower:
        return "timeout"
    if "not attached" in lower or "detached" in lower:
        return "detached"
    if "target closed" in lower:
        return "target_closed"
    if "intercepts pointer events" in lower or "click intercepted" in lower:
        return "click_intercepted"
    if "not visible" in lower:
        return "not_visible"
    if "not enabled" in lower:
        return "not_enabled"
    return "non_transient_error"



_ARTIFACTS_DIR = Path("artifacts")


# JS run in the page to extract data tables for table assertions. Returns
# [{headers:[...], rows:[{header: cellText}], kind}]. Handles native <table>,
# Ant Design .ant-table (header/body split across two inner <table>s), and ARIA
# role=table/grid. Cells are mapped to headers by column index.
_EXTRACT_TABLES_JS = r"""
() => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const tables = [];
  const seenTables = new Set();

  const pushRows = (headers, rowEls, cellSel) => {
    const rows = [];
    rowEls.forEach((tr) => {
      if (tr.getAttribute && tr.getAttribute('aria-hidden') === 'true') return;
      const cells = Array.from(tr.querySelectorAll(cellSel)).map((c) => norm(c.textContent));
      if (!cells.length) return;
      const row = {};
      headers.forEach((h, i) => { row[h] = cells[i] != null ? cells[i] : ''; });
      rows.push(row);
    });
    return rows;
  };

  // 1) Ant Design tables (scope by container; header & body are separate tables).
  document.querySelectorAll('.ant-table').forEach((t) => {
    const headers = Array.from(t.querySelectorAll('.ant-table-thead th')).map((th) => norm(th.textContent));
    if (!headers.length) return;
    const rowEls = Array.from(t.querySelectorAll('.ant-table-tbody tr'));
    const rows = pushRows(headers, rowEls, 'td');
    tables.push({ headers, rows, kind: 'ant' });
    t.querySelectorAll('table').forEach((x) => seenTables.add(x));
  });

  // 2) Native <table> not already covered by an Ant container.
  document.querySelectorAll('table').forEach((t) => {
    if (seenTables.has(t) || t.closest('.ant-table')) return;
    let headers = Array.from(t.querySelectorAll('thead th')).map((th) => norm(th.textContent));
    if (!headers.length) {
      const first = t.querySelector('tr');
      if (first) headers = Array.from(first.querySelectorAll('th,td')).map((c) => norm(c.textContent));
    }
    if (!headers.length) return;
    const bodyRows = t.querySelectorAll('tbody tr');
    const rowEls = Array.from(bodyRows.length ? bodyRows : t.querySelectorAll('tr'));
    const rows = pushRows(headers, rowEls, 'td');
    tables.push({ headers, rows, kind: 'native' });
  });

  // 3) ARIA grid/table built from non-table elements.
  document.querySelectorAll('[role="table"], [role="grid"]').forEach((t) => {
    if (t.tagName === 'TABLE' || t.closest('.ant-table')) return;
    const headers = Array.from(t.querySelectorAll('[role="columnheader"]')).map((c) => norm(c.textContent));
    if (!headers.length) return;
    const rowEls = Array.from(t.querySelectorAll('[role="row"]'));
    const rows = pushRows(headers, rowEls, '[role="gridcell"], [role="cell"]');
    tables.push({ headers, rows, kind: 'aria' });
  });

  return tables;
}
"""


# JS run in the page to pick the best dropdown/select trigger for a step. Scores
# each visible select/combobox by label (strongest), displayed value, placeholder
# and text against the target phrase + value, marks the winner with a temporary
# attribute, and returns {selector, ...}. Lets a "select X from the Y dropdown"
# step resolve a nameless custom combobox by its surrounding context.
_FIND_SELECT_TRIGGER_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const valN = norm(args && args.value);
  const tokens = phrase.split(' ').filter((t) => t.length > 2);

  const SEL = 'select, [role="combobox"], .ant-select, .MuiSelect-select, [class*="select__control"]';
  let els = Array.from(document.querySelectorAll(SEL))
    .filter((e) => !e.matches('.ant-select-selection-search-input')); // use the container, not inner input
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const st = window.getComputedStyle(e);
    return st.visibility !== 'hidden' && st.display !== 'none';
  };
  els = els.filter(visible);
  // De-duplicate nested matches (e.g. a [role=combobox] inside an .ant-select).
  els = els.filter((e) => !els.some((o) => o !== e && o.contains(e)));
  if (!els.length) return null;

  const textOf = (n) => norm(n && (n.getAttribute && n.getAttribute('title') || n.textContent));

  const labelText = (e) => {
    const parts = [];
    if (e.id) {
      const l = document.querySelector('label[for="' + (window.CSS ? CSS.escape(e.id) : e.id) + '"]');
      if (l) parts.push(l.textContent);
    }
    if (e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const lb = e.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.textContent); });
    const fi = e.closest('.ant-form-item, .ant-row, .form-group, [class*="form-item"], [class*="field"]');
    if (fi) { const l = fi.querySelector('label, .ant-form-item-label, [class*="label"]'); if (l) parts.push(l.textContent); }
    let p = e.previousElementSibling, hops = 0;
    while (p && hops < 3) { if (p.tagName === 'LABEL' || /label/i.test(p.className)) parts.push(p.textContent); p = p.previousElementSibling; hops++; }
    return norm(parts.join(' '));
  };
  const displayed = (e) => {
    const item = e.querySelector('.ant-select-selection-item');
    if (item) return textOf(item);
    if (e.tagName === 'SELECT') { const o = e.options && e.options[e.selectedIndex]; return norm(o ? o.text : ''); }
    const inp = e.querySelector('input'); if (inp && inp.value) return norm(inp.value);
    return norm(e.textContent);
  };
  const placeholder = (e) => { const inp = e.querySelector('input'); return norm((inp && inp.placeholder) || e.getAttribute('placeholder') || ''); };

  const overlap = (txt) => { if (!tokens.length || !txt) return 0; let n = 0; tokens.forEach((t) => { if (txt.includes(t)) n++; }); return n / tokens.length; };

  let best = null, bestScore = -1;
  els.forEach((e, i) => {
    const lbl = labelText(e), disp = displayed(e), ph = placeholder(e);
    let score = 0;
    score += 3.0 * overlap(lbl);                 // associated label — strongest signal
    score += 0.8 * overlap(ph);                  // placeholder hint
    score += 0.5 * overlap(disp);                // displayed-text hint
    if (valN && disp === valN) score += 1.5;     // already shows the value we want
    score += (els.length - i) * 0.001;           // tiny earlier-in-DOM tie-breaker
    if (score > bestScore) { bestScore = score; best = e; }
  });
  if (!best) return null;

  document.querySelectorAll('[data-bg-select]').forEach((n) => n.removeAttribute('data-bg-select'));
  best.setAttribute('data-bg-select', '1');
  return { selector: '[data-bg-select="1"]', score: bestScore, count: els.length,
           label: labelText(best), displayed: displayed(best) };
}
"""


# Phase 22E-6: roles that toggle in-page state (or open a popup) and never
# trigger a page navigation per ARIA semantics. Clicking one of these skips
# the post-click wait_for_url probe in _do_click, which otherwise burns its
# full 5 s timeout on every such click.
_NON_NAVIGATING_ROLES = {
    "radio",
    "checkbox",
    "switch",
    "option",
    "tab",
    "combobox",
    "menuitemcheckbox",
    "menuitemradio",
    "slider",
    "spinbutton",
}


def _target_role(target: ResolvedTarget | None) -> str | None:
    """Best-effort ARIA role of the resolved target.

    Prefers the resolver-supplied ``metadata["role"]``; falls back to parsing
    a ``role=<role>[name="..."]`` ref. Returns None when neither is available
    (CSS / text refs), in which case callers must assume navigation is
    possible.
    """
    if target is None:
        return None
    role = target.metadata.get("role")
    if role:
        return str(role).strip().lower()
    ref = target.ref or ""
    if ref.startswith("role="):
        return _NAME_RE.sub("", ref[len("role="):]).strip().lower()
    return None


# Phase 22D-3: action dispatch table. Each handler is bound on the adapter
# instance and receives (plan, locator, timeout, target). Keep this table flat
# and closed — new action types are added explicitly so unsupported plans
# surface as a clear error rather than a silent no-op.
_ACTION_DISPATCH = {
    "click":   lambda self, plan, locator, timeout, target: self._do_click(plan, locator, timeout, target),
    "tap":     lambda self, plan, locator, timeout, target: self._do_click(plan, locator, timeout, target),
    "type":    lambda self, plan, locator, timeout, target: self._do_type(plan, locator, timeout),
    "select":  lambda self, plan, locator, timeout, target: self._do_select(plan, locator, timeout),
    "upload":  lambda self, plan, locator, timeout, target: self._do_upload(plan, locator, timeout),
    "check":   lambda self, plan, locator, timeout, target: self._do_check(plan, locator, timeout),
    "uncheck": lambda self, plan, locator, timeout, target: self._do_uncheck(plan, locator, timeout),
    "scroll":  lambda self, plan, locator, timeout, target: self._do_scroll(plan, locator, timeout),
    "set":     lambda self, plan, locator, timeout, target: self._do_set(plan, locator, timeout),
    "hover":   lambda self, plan, locator, timeout, target: self._do_hover(plan, locator, timeout),
}


class PlaywrightAdapter(BaseAdapter):
    """
    Playwright-based adapter for the web channel.

    Args:
        page: A Playwright Page object (sync or async — async assumed here).
    """

    def __init__(self, page) -> None:  # page: playwright.async_api.Page
        self._page = page
        # W4: start recording responses on this page (idempotent per page) so a
        # later network assertion can confirm a backend call happened.
        _ensure_response_recorder(page)

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
                # Cross-document content (iframes) is invisible to the main
                # frame's snapshot, so append each child frame's snapshot. This
                # only makes elements *discoverable* by the resolvers; execution
                # routes into the owning frame (see _resolve_action_locator).
                if request.include_frames:
                    frame_snapshots = await self._collect_frame_snapshots()
                    if frame_snapshots:
                        a11y_snapshot = "\n".join([a11y_snapshot or "", *frame_snapshots]).strip()
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

        # X3: a target with an explicit point bypasses locator resolution —
        # click the raw coordinate (canvas / image-only / custom-drawn UI from a
        # vision/OCR target with no element mapping).
        if target.point is not None:
            return await self._execute_coordinate_action(plan, target, t0)

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
                locator = await self._resolve_action_locator(ref)
                wait_start = time.monotonic()
                await self._wait_for_mode(locator, wait_for, timeout)
                wait_duration_ms = int((time.monotonic() - wait_start) * 1000)
                if wait_used:
                    target.metadata["wait_used"] = True
                    target.metadata["wait_mode"] = wait_mode
                    target.metadata["wait_outcome"] = "success"
                    target.metadata["wait_adapter"] = "playwright"
                    target.metadata["wait_duration_ms"] = wait_duration_ms
                await self._execute_action(plan=plan, locator=locator, timeout=timeout, target=target)

                duration_ms = int((time.monotonic() - t0) * 1000)
                target.metadata["retry_attempts"] = max(0, attempts - 1)
                target.metadata["retry_transient"] = bool(last_transient)
                target.metadata["retry_reason"] = _sanitize_retry_reason(last_exc) if last_exc else "none"
                target.metadata["retry_adapter"] = "playwright"
                return ExecutionResult(
                    success=True,
                    duration_ms=duration_ms,
                    element_ref=ref,
                )
            except Exception as exc:
                last_exc = exc
                last_transient = _is_transient_execution_error(exc)
                if attempts <= retries and last_transient:
                    logger.info(
                        "PlaywrightAdapter.execute transient failure (attempt %s/%s): %s",
                        attempts,
                        retries + 1,
                        exc,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                duration_ms = int((time.monotonic() - t0) * 1000)
                logger.error("Execution failed for ref=%r: %s", ref, exc)
                if wait_used:
                    target.metadata["wait_used"] = True
                    target.metadata["wait_mode"] = wait_mode
                    target.metadata["wait_outcome"] = "failed"
                    target.metadata["wait_adapter"] = "playwright"
                target.metadata["retry_attempts"] = max(0, attempts - 1)
                target.metadata["retry_transient"] = bool(last_transient)
                target.metadata["retry_reason"] = _sanitize_retry_reason(exc)
                target.metadata["retry_adapter"] = "playwright"
                return ExecutionResult(
                    success=False,
                    duration_ms=duration_ms,
                    element_ref=ref,
                    error=str(exc),
                )

    async def _execute_coordinate_action(
        self, plan: ActionPlan, target: ResolvedTarget, t0: float
    ) -> ExecutionResult:
        """Click ``target.point`` via the Playwright mouse (X3).

        Only click/tap are coordinate-actionable; typing/selecting need a real
        element. Stamps ``coordinate_click`` metadata so reports show the step
        used the fallback rather than an element.
        """
        ref = target.ref
        point = normalize_point(target.point)
        if point is None or plan.action_type not in COORDINATE_CLICK_ACTIONS:
            duration_ms = int((time.monotonic() - t0) * 1000)
            reason = (
                f"action {plan.action_type!r} is not coordinate-clickable"
                if point is not None
                else f"malformed coordinate point {target.point!r}"
            )
            return ExecutionResult(
                success=False, duration_ms=duration_ms, element_ref=ref, error=reason
            )

        x, y = point
        try:
            await self._page.mouse.click(x, y)
            duration_ms = int((time.monotonic() - t0) * 1000)
            target.metadata["coordinate_click"] = True
            target.metadata["coordinate_point"] = [x, y]
            target.metadata["coordinate_adapter"] = "playwright"
            return ExecutionResult(success=True, duration_ms=duration_ms, element_ref=ref)
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("Coordinate click failed at (%s, %s): %s", x, y, exc)
            return ExecutionResult(
                success=False, duration_ms=duration_ms, element_ref=ref, error=str(exc)
            )

    async def _wait_for_mode(self, locator, wait_for: str | None, timeout: int) -> None:
        if not wait_for:
            return

        mode = str(wait_for).strip().lower()
        if mode in _WAIT_STATES:
            await locator.wait_for(state=mode, timeout=timeout)
            return

        if mode == "enabled":
            await locator.wait_for(state="attached", timeout=timeout)
            handle = await locator.element_handle(timeout=timeout)
            if handle is None:
                raise TimeoutError("Element handle not found for enabled wait")
            is_enabled = await handle.is_enabled()
            if not is_enabled:
                raise TimeoutError("Element not enabled")
            return

        raise ValueError(f"Unsupported wait_for mode for Playwright: {wait_for}")

    async def _execute_action(
        self, plan: ActionPlan, locator, timeout: int, target: ResolvedTarget | None = None
    ) -> None:
        handler = _ACTION_DISPATCH.get(plan.action_type)
        if handler is None:
            raise ValueError(f"Unsupported action_type for Playwright execute: {plan.action_type}")
        try:
            await handler(self, plan, locator, timeout, target)
        except Exception as exc:
            # A resolved ref can still match more than one DOM node (e.g.
            # text="Login" on a page with a heading and a button). Reading
            # already takes .first; mirror that for actions instead of failing
            # the whole step on a strict-mode violation.
            if not _is_strict_mode_violation(exc):
                raise
            logger.info(
                "Strict-mode violation on %s — retrying against the first match",
                plan.action_type,
            )
            await handler(self, plan, locator.first, timeout, target)
            if target is not None:
                target.metadata["strict_mode_fallback_first"] = True

    async def _do_click(
        self, plan: ActionPlan, locator, timeout: int, target: ResolvedTarget | None = None
    ) -> None:
        # Record URL before click so we can detect navigation afterwards.
        url_before = self._page.url
        await locator.click(timeout=timeout)
        # Toggle-style roles (radio, checkbox, tab, ...) flip in-page state
        # and never navigate, so the URL probe below would always burn its
        # full 5 s timeout. Skip it for those roles.
        role = _target_role(target)
        if role in _NON_NAVIGATING_ROLES:
            if target is not None:
                target.metadata["nav_wait_skipped"] = True
                target.metadata["nav_wait_skipped_role"] = role
            return

        nav_wait_ms = int(getattr(plan.options, "nav_wait_ms", _DEFAULT_NAV_WAIT_MS) or 0)
        if nav_wait_ms <= 0:
            return

        # Two-phase wait. Phase 1: cheaply detect whether a navigation *commits*
        # within nav_wait_ms — the common AJAX/SPA click that never navigates
        # pays at most this bounded cost instead of the full action timeout.
        # Phase 2: only when a navigation did start, wait for the new document
        # to be ready (using the full action timeout) so the next step doesn't
        # race a half-loaded page.
        try:
            await self._page.wait_for_url(
                lambda url: url != url_before,
                wait_until="commit",
                timeout=nav_wait_ms,
            )
        except Exception:
            return  # No navigation committed — in-page click, nothing to wait for

        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass  # Document settle is best-effort; the URL already changed.

    async def _do_type(self, plan: ActionPlan, locator, timeout: int) -> None:
        value = plan.input_value or ""
        await locator.fill(value, timeout=timeout)

    async def _do_select(self, plan: ActionPlan, locator, timeout: int) -> None:
        value = plan.input_value or ""

        # Native <select> vs. custom combobox. Playwright's select_option() only
        # drives a real <select>; the div/button-based comboboxes shipped by
        # Ant Design / MUI / Angular CDK / React-Select expose role="combobox"
        # but cannot be selected that way — you must open the popup and click an
        # option. Detect by tag name (both surface as role=combobox in the a11y
        # tree, so role alone can't tell them apart). evaluate() is unavailable
        # on test doubles; treat that (None) as native to stay backward
        # compatible with the legacy select_option path.
        tag = await self._safe_tag_name(locator)
        if tag is not None and tag != "select":
            await self._select_from_custom_combobox(locator, value, timeout)
            return

        # Native <select>. Testers write the *visible* option ("France"), but a
        # <select> often carries a different value attribute
        # (<option value="FR">France</option>). Try value-match first (fast path
        # / backward compatible), then fall back to label-match so
        # natural-language selection works either way.
        try:
            await locator.select_option(value, timeout=timeout)
        except Exception:
            await locator.select_option(label=value, timeout=timeout)

    async def _safe_tag_name(self, locator) -> str | None:
        """Lower-cased tagName of the resolved element, or None if undetectable.

        Returns None on any failure (e.g. evaluate() missing on a test double,
        or a strict-mode multi-match) so callers can fall back to legacy
        behaviour rather than erroring.
        """
        try:
            tag = await locator.evaluate("el => el.tagName")
        except Exception:
            return None
        return (tag or "").strip().lower() or None

    async def _select_from_custom_combobox(self, trigger, value: str, timeout: int) -> None:
        """Select ``value`` from a non-native combobox (Ant Design / MUI / CDK).

        Opens the trigger, then clicks the matching option. The listbox is
        frequently portal-rendered to <body> (out of the trigger's subtree), so
        options are searched from the page, not the trigger. Targeting the option
        (not the trigger) also sidesteps the common ambiguity where the trigger
        displays the currently-selected value and an option carries that same
        text.

        Resolution order (first hit wins):
          1. ARIA-correct widgets expose role="option"/"menuitem" — match by name.
          2. Library option rows that are role-less. Ant Design's rc-select
             renders the *visible* option as
             ``<div class="ant-select-item-option" title="V">`` (content in a
             ``.ant-select-item-option-content`` child) and its aria-controls
             points at a separate off-screen listbox, so it is matched directly
             by option class + title/text. The trigger's own label is a different
             class (``.ant-select-selection-item``) and is never matched.
          3. Generic: any element with the exact text, scoped to an open popup
             (listbox/menu/dropdown), then the aria-controls/aria-owns listbox.
        """
        await self._open_combobox(trigger, timeout)

        probe = min(timeout, 3000)
        last_exc: Exception | None = None

        # Wait (bounded, best-effort) for the popup to materialize after opening,
        # so the count()-guarded attempts below see a settled DOM rather than
        # racing an animating dropdown.
        opened = self._page.locator(
            '[role="option"], [role="menuitem"], .ant-select-item-option, '
            '[role="listbox"], [role="menu"], .ant-select-dropdown'
        )
        try:
            await opened.first.wait_for(state="visible", timeout=probe)
        except Exception:  # noqa: BLE001 — proceed; the attempts still guard themselves
            pass

        attempts: list = []

        # 1) Standard ARIA listbox / menu options.
        attempts += [
            self._page.get_by_role("option", name=value, exact=True),
            self._page.get_by_role("option", name=value),
            self._page.get_by_role("menuitem", name=value, exact=True),
            self._page.get_by_role("menuitem", name=value),
        ]

        # 2) Role-less library option rows (Ant Design rc-select & lookalikes):
        #    <div class="ant-select-item-option" title="V">. The trigger's own
        #    label is .ant-select-selection-item, so it is never matched here.
        esc = value.replace("\\", "\\\\").replace('"', '\\"')
        attempts += [
            self._page.locator(f'.ant-select-item-option[title="{esc}"]'),
            self._page.locator(".ant-select-item-option", has_text=value),
        ]

        # 3a) Generic: exact text/title inside any open popup container.
        popup = self._page.locator(
            '[role="listbox"], [role="menu"], .ant-select-dropdown, '
            '[class*="dropdown"], [class*="menu"], [class*="popover"], [class*="popup"]'
        )
        attempts += [
            popup.get_by_text(value, exact=True),
            popup.get_by_title(value, exact=True),
        ]

        # 3b) The listbox the trigger explicitly owns (aria-controls / aria-owns).
        container = await self._owned_listbox(trigger)
        if container is not None:
            attempts += [
                container.get_by_text(value, exact=True),
                container.get_by_title(value, exact=True),
                container.get_by_text(value),
            ]

        # count() returns immediately (no implicit wait), so non-matching shapes
        # are skipped instantly instead of each burning the probe timeout — only
        # a shape that actually matches is clicked.
        for option in attempts:
            try:
                if await option.count() == 0:
                    continue
                await option.first.click(timeout=probe)
                return
            except Exception as exc:  # noqa: BLE001 — try the next option shape
                last_exc = exc

        raise ValueError(
            f"could not find a dropdown option matching {value!r} after opening "
            f"the combobox (tried role=option/menuitem, .ant-select-item-option "
            f"by title/text, open-popup text/title, and the aria-controls listbox)"
        ) from last_exc

    async def _owned_listbox(self, trigger):
        """Locator for the popup a combobox owns via aria-controls / aria-owns.

        Returns None when the trigger advertises no owned popup. The id is
        matched with an attribute selector (not ``#id``) so ids containing
        characters that are special in CSS still resolve, and the popup is found
        wherever it is portal-rendered.
        """
        try:
            node = trigger.first
            owned = await node.get_attribute("aria-controls")
            if not owned:
                owned = await node.get_attribute("aria-owns")
        except Exception:
            return None
        if not owned:
            return None
        # aria-controls/owns may list several ids; the listbox is the first.
        listbox_id = owned.split()[0]
        return self._page.locator(f'[id="{listbox_id}"]')

    async def _open_combobox(self, trigger, timeout: int) -> None:
        """Click a combobox trigger open, forcing past overlay interception.

        Ant Design (and similar) overlay a selection ``<span>`` on top of the
        inner ``role="combobox"`` ``<input>``; Playwright reports that span as
        intercepting the click and a normal click times out. The overlay is part
        of the same widget, so a force click at the trigger's position opens the
        listbox exactly as a human click would. A short normal-click probe is
        tried first so genuinely-clickable triggers (``<button>``/``<div>``
        comboboxes) keep their full actionability checks.
        """
        probe = min(timeout, 1500)
        try:
            await trigger.click(timeout=probe)
        except Exception:
            await trigger.click(timeout=timeout, force=True)

    async def _do_upload(self, plan: ActionPlan, locator, timeout: int) -> None:
        value = plan.input_value
        if not value:
            raise ValueError(
                "upload action requires input_value to be a file path "
                "(e.g. '/tmp/resume.pdf' or a list of paths)"
            )
        await locator.set_input_files(value, timeout=timeout)

    async def _do_check(self, plan: ActionPlan, locator, timeout: int) -> None:
        await locator.check(timeout=timeout)

    async def _do_uncheck(self, plan: ActionPlan, locator, timeout: int) -> None:
        await locator.uncheck(timeout=timeout)

    async def _do_scroll(self, plan: ActionPlan, locator, timeout: int) -> None:
        await locator.scroll_into_view_if_needed(timeout=timeout)

    async def _do_hover(self, plan: ActionPlan, locator, timeout: int) -> None:
        """Hover the resolved element — e.g. to reveal a hover-triggered menu."""
        await locator.hover(timeout=timeout)

    async def _do_set(self, plan: ActionPlan, locator, timeout: int) -> None:
        """Set a numeric / range value on the resolved element.

        Used for "Set Volume to 75". Drives the value via JS so it works for
        ``<input type="range">``, ARIA sliders with a backing native input,
        and MUI's hidden-input slider pattern. Dispatches ``input`` +
        ``change`` so React/Vue listeners pick up the new value.
        """
        if plan.input_value is None:
            raise ValueError("set action requires input_value (the target value)")

        value = str(plan.input_value)
        await locator.wait_for(state="attached", timeout=timeout)
        await locator.first.evaluate(
            """(el, v) => {
                // Find the underlying native input if the resolver landed on
                // a styled wrapper (MUI slider thumb / role=slider on a div).
                const input = (el.tagName === 'INPUT')
                    ? el
                    : (el.querySelector && el.querySelector('input')) || el;
                if ('value' in input) input.value = v;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            value,
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

    async def wait_until_stable(
        self,
        *,
        quiet_ms: int = 400,
        timeout_ms: int = 5_000,
        spinner_selectors: list[str] | None = None,
    ) -> dict:
        """Wait until the page settles before resolution (W2).

        Settled means: no in-flight network (Playwright ``networkidle``), no DOM
        mutations for ``quiet_ms``, and no visible loading indicator from
        ``spinner_selectors`` — bounded by ``timeout_ms``. Best-effort: returns a
        diagnostic dict and never raises for timeouts.
        """
        spinner_selectors = spinner_selectors or []
        diag: dict = {
            "adapter": "playwright",
            "quiet_ms": quiet_ms,
            "timeout_ms": timeout_ms,
        }

        # 1) Network idle (best-effort; a long-poll/websocket page may never idle).
        network_idle = True
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            network_idle = False

        # 2) DOM-quiet + spinner-gone via an in-page MutationObserver loop.
        try:
            result = await self._page.evaluate(
                _STABILITY_JS,
                {"quietMs": quiet_ms, "timeoutMs": timeout_ms, "spinnerSelectors": spinner_selectors},
            )
        except Exception as exc:
            diag.update({"outcome": "error", "network_idle": network_idle, "error": str(exc)})
            return diag

        diag.update(
            {
                "outcome": "stable" if result.get("stable") else "timeout",
                "network_idle": network_idle,
                "dom_quiet": bool(result.get("domQuiet")),
                "spinner_gone": bool(result.get("spinnerGone")),
                "waited_ms": int(result.get("waitedMs", 0)),
            }
        )
        return diag

    async def extract_tables(self) -> list[dict]:
        """Extract data tables from the page for table assertions.

        Handles native ``<table>`` (thead/tbody), Ant Design ``.ant-table``
        (which splits the header and body into separate inner tables, so it is
        scoped by the ``.ant-table`` container), and ARIA ``role=table``/``grid``.
        Returns ``[{"headers": [str], "rows": [{header: cell_text}], "kind": str}]``.
        """
        return await self._page.evaluate(_EXTRACT_TABLES_JS)

    async def find_select_trigger(self, target_phrase: str, value: str) -> str | None:
        """Resolve a dropdown/select trigger from the DOM and return a selector.

        A last-resort path for custom comboboxes (Ant Design / MUI / CDK) whose
        accessible name is too poor for the a11y snapshot to ground uniquely.
        Scores every visible select/combobox by its associated label, placeholder,
        currently-displayed value, and role/text against the step's target phrase
        and value, marks the best match with a temporary attribute, and returns a
        selector for it. Returns None when no select-like control is visible.
        """
        result = await self._page.evaluate(
            _FIND_SELECT_TRIGGER_JS, {"phrase": target_phrase or "", "value": value or ""}
        )
        if not result:
            return None
        logger.debug("find_select_trigger %r/%r -> %s", target_phrase, value, result)
        return result.get("selector")

    async def assert_network(self, matcher: dict, *, timeout_ms: int = 5_000) -> tuple[bool, str]:
        """Assert a backend response matching ``matcher`` occurred (W4).

        Checks responses already recorded on this page (since the first Bubblegum
        step); if none match yet, waits up to ``timeout_ms`` for a future one.
        Returns (passed, human-readable detail).
        """
        from bubblegum.core.network import (
            describe_matcher,
            describe_record,
            find_matching_response,
            response_matches,
        )

        log = _ensure_response_recorder(self._page)
        found = find_matching_response(log, matcher)
        if found is not None:
            return True, f"matched {describe_record(found)}"

        # Not seen yet — wait for a future matching response within the timeout.
        try:
            resp = await self._page.wait_for_response(
                lambda r: response_matches(
                    {"method": r.request.method, "url": r.url, "status": r.status}, matcher
                ),
                timeout=timeout_ms,
            )
            return True, (
                f"matched {resp.request.method} {resp.url} {resp.status}"
            )
        except Exception:
            return False, (
                f"no response matching '{describe_matcher(matcher)}' "
                f"({len(log)} response(s) seen)"
            )

    async def run_axe(
        self,
        *,
        axe_script: str | None = None,
        axe_url: str | None = None,
    ) -> dict:
        """Inject axe-core and run an accessibility audit against the page.

        Provide either ``axe_script`` (inline JS, the vendored default) or
        ``axe_url`` (a remote build). Returns the raw ``axe.run()`` result dict
        (with ``violations``, ``passes`` etc.). Browser-only; parsing/filtering
        of the result happens in ``bubblegum.core.a11y``.
        """
        if axe_url:
            await self._page.add_script_tag(url=axe_url)
        elif axe_script:
            await self._page.add_script_tag(content=axe_script)
        else:
            raise ValueError("run_axe requires axe_script or axe_url")
        # axe.run() returns a Promise; Playwright awaits it and returns the value.
        return await self._page.evaluate("() => axe.run(document)")

    async def screenshot_bytes(self, *, full_page: bool = False) -> bytes:
        """Capture a PNG screenshot and return the raw bytes (no file written).

        Used by the visual-regression assertion (V1), which manages its own
        baseline/diff files under ``.bubblegum/baselines/``.
        """
        return await self._page.screenshot(type="png", full_page=full_page)

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

    def _resolve_locator(self, ref: str, root=None):
        """
        Convert a ref string into a Playwright Locator.

        ``root`` is the search context: the page by default, or a child Frame
        when routing into an iframe (Frame exposes the same get_by_role /
        get_by_text / locator API as Page).

        Supported ref formats:
          role=button[name="Login"]    → root.get_by_role("button", name="Login")
          text="Login"                 → root.get_by_text("Login", exact=True)
          #id / .class / [attr]        → root.locator(ref)  (CSS / XPath pass-through)
          role=button                  → root.get_by_role("button")
        """
        root = root if root is not None else self._page

        # Semantic role locator: role=<role>[name="<name>"]
        if ref.startswith("role="):
            role_part = ref[len("role="):]
            name_match = _NAME_RE.search(role_part)
            role = _NAME_RE.sub("", role_part).strip()
            if name_match:
                name = name_match.group(1)
                return root.get_by_role(role, name=name)
            return root.get_by_role(role)

        # Exact text locator: text="Login"
        if ref.startswith('text="') and ref.endswith('"'):
            label = ref[6:-1]
            return root.get_by_text(label, exact=True)

        if ref.startswith("text="):
            label = ref[5:]
            return root.get_by_text(label, exact=True)

        # CSS / XPath / id pass-through
        return root.locator(ref)

    def _child_frames(self) -> list:
        """Return the page's child frames (excluding the main frame).

        Guarded so it is a no-op for frameless pages and for the lightweight
        fake pages used in unit tests (which expose no ``frames`` attribute).
        """
        page = self._page
        frames = getattr(page, "frames", None)
        if not frames:
            return []
        main = getattr(page, "main_frame", None)
        try:
            return [f for f in frames if f is not main]
        except Exception:
            return []

    async def _collect_frame_snapshots(self) -> list[str]:
        """Capture the aria snapshot of each child frame's body."""
        snapshots: list[str] = []
        for frame in self._child_frames():
            try:
                snap = await frame.locator("body").aria_snapshot()
            except Exception as exc:
                logger.debug("frame aria_snapshot() skipped: %s", exc)
                continue
            if snap:
                snapshots.append(snap)
        return snapshots

    async def _resolve_action_locator(self, ref: str):
        """Resolve ``ref`` against the main frame, falling back to child frames.

        The main frame is preferred (and returned directly when the page has no
        child frames, which keeps the frameless fast-path identical to before).
        Otherwise the locator is routed into the first child frame that actually
        contains a match — this is how an iframe element resolved from the
        merged snapshot becomes executable.
        """
        main = self._resolve_locator(ref)
        frames = self._child_frames()
        if not frames:
            return main

        try:
            if await main.count() > 0:
                return main
        except Exception:
            return main

        for frame in frames:
            try:
                candidate = self._resolve_locator(ref, root=frame)
                if await candidate.count() > 0:
                    return candidate
            except Exception:
                continue
        return main

    async def extract_text(self, ref: str, timeout_ms: int = 10_000) -> str:
        """Read the inner text of the element identified by ``ref``.

        Frame-aware (routes into the owning iframe when needed) and uses
        ``.first`` so a ref matching multiple nodes does not raise.
        """
        locator = await self._resolve_action_locator(ref)
        return await locator.first.inner_text(timeout=timeout_ms)

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
                # Check raw page text (not HTML) so the caller gets a useful message.
                try:
                    page_text = await self._page.inner_text("body")
                except Exception:
                    page_text = ""
                found = expected.lower() in page_text.lower()
                actual = expected if found else f"text not found on page (url={self._page.url})"
                return (found, actual)

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
import weakref  # noqa: E402

_NAME_RE = re.compile(r'\[name="([^"]+)"\]')

# W4: per-page response logs. Keyed weakly so logs are GC'd with their page.
_RESPONSE_LOGS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _ensure_response_recorder(page) -> list[dict]:
    """Attach a one-time response listener to ``page`` and return its log.

    Idempotent per page. Defensive: returns an empty list (and skips wiring) if
    the page is not hashable/weak-referenceable or has no ``.on`` — so fake test
    pages and non-Playwright handles never break adapter construction.
    """
    try:
        existing = _RESPONSE_LOGS.get(page)
        if existing is not None:
            return existing
        log: list[dict] = []
        _RESPONSE_LOGS[page] = log
    except TypeError:
        return []

    on = getattr(page, "on", None)
    if callable(on):
        def _on_response(response) -> None:
            try:
                log.append(
                    {
                        "method": response.request.method,
                        "url": response.url,
                        "status": int(response.status),
                    }
                )
            except Exception:  # noqa: BLE001 — never let logging break the page
                pass

        try:
            on("response", _on_response)
        except Exception:  # noqa: BLE001
            pass
    return log

# In-page quiescence probe (W2): resolves once the DOM has been mutation-free
# for quietMs AND no spinner selector is visible, or when timeoutMs elapses.
_STABILITY_JS = """
(opts) => new Promise((resolve) => {
  const quietMs = opts.quietMs, timeoutMs = opts.timeoutMs;
  const spinnerSelectors = opts.spinnerSelectors || [];
  const start = Date.now();
  let lastMutation = Date.now();
  let observer;
  try {
    observer = new MutationObserver(() => { lastMutation = Date.now(); });
    observer.observe(document.documentElement || document, {
      subtree: true, childList: true, attributes: true, characterData: true
    });
  } catch (e) { observer = null; }
  function spinnerVisible() {
    for (const sel of spinnerSelectors) {
      let els;
      try { els = document.querySelectorAll(sel); } catch (e) { continue; }
      for (const el of els) {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style && style.display !== 'none' && style.visibility !== 'hidden'
            && style.opacity !== '0' && rect.width > 0 && rect.height > 0) {
          return true;
        }
      }
    }
    return false;
  }
  function finish(stable, domQuiet, spinnerGone) {
    if (observer) { try { observer.disconnect(); } catch (e) {} }
    resolve({ stable, domQuiet, spinnerGone, waitedMs: Date.now() - start });
  }
  (function check() {
    const now = Date.now();
    const domQuiet = (now - lastMutation) >= quietMs;
    const spinnerGone = !spinnerVisible();
    if (domQuiet && spinnerGone) return finish(true, true, true);
    if (now - start >= timeoutMs) return finish(false, domQuiet, spinnerGone);
    setTimeout(check, 50);
  })();
})
"""
