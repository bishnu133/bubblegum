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
# JS snippet (spliced into the input/radio/checkbox resolvers via the
# `__SECTION_JS` placeholder): defines `sectionText(e)` — the heading(s) of the
# form section a control lives in. Two similar sections ("Eligibility" /
# "Recommendation") often share option labels (Male/Female) and field labels
# (Minimum Age), so the option/field text ties and DOM order wrongly decides.
# The section heading breaks the tie. We gather BOTH the nearest section
# container's own heading (an Ant card head-title / <legend> / <hN>) AND the
# nearest *preceding* block heading (e.g. a bare <h4>Eligibility</h4> that titles
# the block) — because the discriminating word may live in either. We never cross
# into a sibling SECTION while climbing, so one section's heading can't leak into
# another's. Headings only, never body text (which would re-introduce the shared
# labels). Relies on `norm` being in scope.
_SECTION_HEADING_JS = r"""
  const sectionText = (e) => {
    const parts = [];
    const SECTION_SEL = '.ant-card, .MuiCard-root, section, fieldset, [class~="card"], [class~="section"], [role="group"]';
    const isSection = (n) => !!(n && n.matches && n.matches(SECTION_SEL));
    // (a) the nearest section container's own heading. Whole-token class match
    //     (`~=`) lands on the real card (class "ant-card"), not its inner
    //     "ant-card-body" whose head-title sibling would then be missed.
    const card = e.closest(SECTION_SEL);
    if (card) {
      const h = card.querySelector('.ant-card-head-title, legend, h1, h2, h3, h4, h5, h6');
      if (h && (h.textContent || '').trim()) parts.push(h.textContent);
    }
    // (b) the nearest preceding heading, climbing ancestors. Stop at the FIRST
    //     one found, and never look inside a sibling section — either would pull
    //     in a different section's title.
    let a = e, up = 0, done = false;
    while (a && up < 12 && !done) {
      let s = a.previousElementSibling, seen = 0;
      while (s && seen < 4) {
        if (!isSection(s)) {
          if (/^(H[1-6]|LEGEND)$/.test(s.tagName)) {
            const t = (s.textContent || '').trim();
            if (t && t.length <= 60) { parts.push(t); done = true; break; }
          } else {
            const hh = s.querySelector && s.querySelector('h1, h2, h3, h4, h5, h6, legend');
            if (hh && (hh.textContent || '').trim() && !isSection(hh.parentElement)) {
              parts.push(hh.textContent); done = true; break;
            }
          }
        }
        s = s.previousElementSibling; seen++;
      }
      a = a.parentElement; up++;
    }
    return norm(parts.join(' '));
  };
"""




# JS run in the page to pick the best dropdown/select trigger for a step. Scores
# each visible select/combobox by label (strongest), displayed value, placeholder
# and text against the target phrase + value, marks the winner with a temporary
# attribute, and returns {selector, ...}. Lets a "select X from the Y dropdown"
# step resolve a nameless custom combobox by its surrounding context.
_FIND_SELECT_TRIGGER_JS = r"""
(args) => {
  // __bgField: nearest form-item-ish ancestor that actually CONTAINS a label.
  // Ant nests the control in `.ant-form-item-control-input-content`, which also
  // matches [class*="form-item"], so a plain closest() stops there (no label
  // inside) and label-based disambiguation silently fails — every field then
  // ties on DOM order and the first one always wins. Climb until we reach a
  // container that has a label; fall back to closest() when none does.
  const __bgField = (e, sel) => {
    let p = e.parentElement, hops = 0;
    while (p && hops < 15) {
      if (p.matches(sel) && p.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])')) return p;
      p = p.parentElement; hops++;
    }
    return e.closest(sel);
  };
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
    const fi = __bgField(e, '.ant-form-item, .ant-row, .form-group, [class*="form-item"], [class*="field"]');
    if (fi) { const l = fi.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])'); if (l) parts.push(l.textContent); }
    let p = e.previousElementSibling, hops = 0;
    while (p && hops < 3) { if (p.tagName === 'LABEL' || /label/i.test(p.className)) parts.push(p.textContent); p = p.previousElementSibling; hops++; }
    return norm(parts.join(' '));
  };
  // A control is often introduced by a short heading that is NOT a <label for>
  // (a bare <span>Eligibility Tags</span>, a <h4>, a <b>…) sitting before the
  // group that wraps it. Climb a few ancestors and, at each level, read the
  // nearest preceding sibling that looks like a heading (short text, no controls
  // inside). Generic: works for any "group label" pattern, not just Ant.
  const groupHeading = (e) => {
    const parts = [];
    let a = e, up = 0;
    while (a && up < 8) {
      let s = a.previousElementSibling, seen = 0;
      while (s && seen < 3) {
        if (/^(SPAN|LABEL|H[1-6]|B|STRONG|LEGEND|P|DIV)$/.test(s.tagName)) {
          const t = (s.textContent || '').trim();
          if (t && t.length <= 40 && !s.querySelector('input, select, textarea, button, [role="combobox"]')) {
            parts.push(t);
            break;
          }
        }
        s = s.previousElementSibling; seen++;
      }
      a = a.parentElement; up++;
    }
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
    score += 2.0 * overlap(groupHeading(e));     // preceding group heading (not a <label for>)
    score += 0.8 * overlap(ph);                  // placeholder hint
    score += 0.5 * overlap(disp);                // displayed-text hint
    if (valN && disp === valN) score += 1.5;     // already shows the value we want
    // Tie-breaker: when a group heading (e.g. "Eligibility Tags") labels more than
    // one select — a compact qualifier ("All/Any") plus the value picker — the
    // value being selected belongs in the multi-select. Nudge it ahead.
    if (e.matches('.ant-select-multiple') || e.getAttribute('aria-multiselectable') === 'true' || e.multiple) score += 0.3;
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


# JS: resolve a text input / textarea by its surrounding context (label,
# placeholder, name/id, nearby form-item label) for a "type" step whose field
# has no accessible name. Skips ant-select search inputs and disabled fields.
_FIND_INPUT_JS = r"""
(args) => {
  // Nearest form-item-ish ancestor that actually CONTAINS a label — see the
  // note in _FIND_SELECT_TRIGGER_JS. Without this, Ant's nested
  // `.ant-form-item-control-input-content` (which matches [class*="form-item"])
  // swallows closest(), the label comes back empty, and every input ties on DOM
  // order so the first field wins for every phrase.
  const __bgField = (e, sel) => {
    let p = e.parentElement, hops = 0;
    while (p && hops < 15) {
      if (p.matches(sel) && p.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])')) return p;
      p = p.parentElement; hops++;
    }
    return e.closest(sel);
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 2);
  const SEL = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio])'
            + ':not([type=submit]):not([type=button]):not([type=file]):not([type=radio]),'
            + 'textarea, [contenteditable=""], [contenteditable="true"]';
  let els = Array.from(document.querySelectorAll(SEL))
    .filter((e) => !e.classList.contains('ant-select-selection-search-input'));
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  els = els.filter(visible);
  if (!els.length) return null;

  // The VISIBLE label (associated <label>/aria/form-item label) — no name/id.
  // Used to detect when two fields share the same on-screen label ("Minimum Age"
  // in both the Eligibility and Recommendation sections); the section heading
  // then disambiguates. name/id often ALSO encode the section, so they go into
  // the full label used for the final score, but not into the collision test.
  const visibleLabel = (e) => {
    const parts = [];
    if (e.id) {
      const l = document.querySelector('label[for="' + (window.CSS ? CSS.escape(e.id) : e.id) + '"]');
      if (l) parts.push(l.textContent);
    }
    if (e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const lb = e.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.textContent); });
    const fi = __bgField(e, '.ant-form-item, .ant-row, .form-group, [class*="form-item"], [class*="field"]');
    if (fi) { const l = fi.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])'); if (l) parts.push(l.textContent); }
    return norm(parts.join(' '));
  };
  const labelText = (e) => {
    const parts = [visibleLabel(e)];
    if (e.name) parts.push(e.name);
    if (e.id) parts.push(e.id);
    return norm(parts.join(' '));
  };
  __SECTION_JS
  const placeholder = (e) => norm(e.getAttribute('placeholder') || '');
  const overlap = (txt) => { if (!tokens.length || !txt) return 0; let n = 0; tokens.forEach((t) => { if (txt.includes(t)) n++; }); return n / tokens.length; };

  let best = null, bestScore = -1, bestVis = 0, bestSec = '';
  const vis = els.map(visibleLabel);
  els.forEach((e, i) => {
    const secOv = overlap(sectionText(e));
    // Section overlap (weight 1.0 < the label weight 3.0) breaks ties between
    // same-labelled fields in different sections without overriding a field whose
    // own label is a clearly better match.
    let score = 3.0 * overlap(labelText(e)) + 1.2 * overlap(placeholder(e)) + 1.0 * secOv;
    if (e.disabled) score -= 5;             // strongly avoid disabled fields
    score += (els.length - i) * 0.001;      // earlier-in-DOM tie-break
    if (score > bestScore) { bestScore = score; best = e; bestVis = overlap(vis[i]); bestSec = sectionText(e); }
  });
  if (!best || bestScore <= 0) return null;
  // "sectioned": the winner shares its (matched) visible label with at least one
  // other field, and a section heading is what set it apart. This is the signal
  // that lets the caller pre-empt grounding — without it, an ambiguous field
  // would be resolved from the a11y snapshot (which can pick the wrong section).
  let tie = 0;
  els.forEach((e, i) => { if (bestVis > 0 && overlap(vis[i]) >= bestVis) tie++; });
  const sectioned = overlap(bestSec) > 0 && tie >= 2;

  document.querySelectorAll('[data-bg-input]').forEach((n) => n.removeAttribute('data-bg-input'));
  best.setAttribute('data-bg-input', '1');
  return { selector: '[data-bg-input="1"]', label: labelText(best), score: bestScore,
           section: bestSec, sectioned };
}
""".replace("__SECTION_JS", _SECTION_HEADING_JS)


# JS: resolve a rich-text editor (`contenteditable`) for a "type" step by its
# form-item label. RTE widgets (Quill, TinyMCE, ProseMirror, CKEditor, Draft.js)
# render as a bare `[contenteditable]` div with NO `textbox` role and NO
# accessible name, so they are invisible to role-based grounding — the a11y chain
# then mis-matches a nearby valued input instead.
#
# It scores EVERY fillable control (inputs, textareas, contenteditables) by label
# the same way `_FIND_INPUT_JS` does, then claims the step only when the best
# match is a rich-text editor. Comparing against inputs on equal footing is what
# keeps plain-field steps safe: a phrase like "Challenge Name" matches the name
# <input> better than any editor, so a plain input wins and this returns null
# (the normal input path handles it). This relative ranking is robust to phrasing
# — it does not require an exact/full label match — so small differences in how
# the target phrase is decomposed no longer cause a miss.
_FIND_RICH_TEXT_JS = r"""
(args) => {
  const __bgField = (e, sel) => {
    let p = e.parentElement, hops = 0;
    while (p && hops < 15) {
      if (p.matches(sel) && p.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])')) return p;
      p = p.parentElement; hops++;
    }
    return e.closest(sel);
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 2);
  if (!tokens.length) return null;

  const SEL = 'input:not([type=hidden]):not([type=checkbox]):not([type=radio])'
            + ':not([type=submit]):not([type=button]):not([type=file]),'
            + 'textarea, [contenteditable=""], [contenteditable="true"]';
  let els = Array.from(document.querySelectorAll(SEL))
    .filter((e) => !e.classList.contains('ant-select-selection-search-input'));
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  els = els.filter(visible);
  if (!els.length) return null;

  const isCE = (e) => !!(e.isContentEditable || (e.getAttribute && e.getAttribute('contenteditable') !== null && e.getAttribute('contenteditable') !== 'false'));
  const labelText = (e) => {
    const parts = [];
    if (e.getAttribute && e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const lb = e.getAttribute && e.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.textContent); });
    const fi = __bgField(e, '.ant-form-item, .ant-row, .form-group, [class*="form-item"], [class*="field"]');
    if (fi) { const l = fi.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])'); if (l) parts.push(l.textContent); }
    if (e.name) parts.push(e.name);
    if (e.id) parts.push(e.id);
    return norm(parts.join(' '));
  };
  const placeholder = (e) => norm((e.getAttribute && e.getAttribute('placeholder')) || '');
  const overlap = (txt) => { if (!txt) return 0; let n = 0; tokens.forEach((t) => { if (txt.includes(t)) n++; }); return n / tokens.length; };

  let best = null, bestScore = -1;
  els.forEach((e, i) => {
    let score = 3.0 * overlap(labelText(e)) + 1.2 * overlap(placeholder(e));
    if (e.disabled) score -= 5;
    score += (els.length - i) * 0.001;         // earlier-in-DOM tie-break
    if (score > bestScore) { bestScore = score; best = e; }
  });
  // Claim the step only when a rich-text editor is the best fillable match AND it
  // actually matched the phrase's label (guards against a weak editor winning a
  // field of otherwise-nameless controls). Otherwise let the input path run.
  if (!best || !isCE(best) || overlap(labelText(best)) < 0.5) return null;
  document.querySelectorAll('[data-bg-input]').forEach((n) => n.removeAttribute('data-bg-input'));
  best.setAttribute('data-bg-input', '1');
  return { selector: '[data-bg-input="1"]', label: labelText(best), score: bestScore };
}
"""


# JS: resolve a radio option by its label text and return a clickable target +
# its checked state. Radios are commonly a hidden (`opacity:0`) `<input
# type=radio>` inside a styled wrapper/label (Ant `.ant-radio-wrapper`, MUI
# `FormControlLabel`), so name-based grounding misses them and clicking the input
# is unreliable — click the wrapper/label instead. Works for native + Ant + MUI.
_FIND_RADIO_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 1);
  if (!tokens.length) return null;
  // Section context ("… for Eligibility", "… on the Recommendation section").
  // Two sections often carry the SAME option label (Male/Female), so the option
  // text alone ties and DOM order wins — landing on the wrong section. Context
  // tokens that are NOT part of the option label (and not generic action words)
  // disambiguate by matching the nearest section heading (see sectionText below).
  const STOP = new Set(['select','radio','button','buttons','option','the','for','on','in','of','to','a','an','choose','click','pick','set','and','with','sex','gender','value','field']);
  const ctx = norm(args && args.context);
  const ctxTokens = ctx.split(' ')
    .map((t) => t.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, ''))   // strip quotes/punctuation edges
    .filter((t) => t.length > 2 && !STOP.has(t) && tokens.indexOf(t) < 0);

  const els = Array.from(document.querySelectorAll('input[type=radio], [role=radio]'));
  if (!els.length) return null;

  const wrapperOf = (e) => e.closest(
    'label, .ant-radio-wrapper, [class*="radio-wrapper"], [class*="RadioWrapper"],'
    + ' [class*="FormControlLabel"], [class*="form-check"]'
  );
  const shown = (e) => {
    const w = wrapperOf(e) || e;
    const r = w.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(w);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };

  const labelText = (e) => {
    const parts = [];
    const wl = e.closest('label');
    if (wl) parts.push(wl.textContent);
    if (e.id) { const l = document.querySelector('label[for="' + (window.CSS ? CSS.escape(e.id) : e.id) + '"]'); if (l) parts.push(l.textContent); }
    if (e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const lb = e.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.textContent); });
    const w = wrapperOf(e);
    if (w) parts.push(w.textContent);
    if (e.value) parts.push(e.value);
    return norm(parts.join(' '));
  };
  __SECTION_JS
  // Whole-word match, NOT substring: "male" must not match "female" (which
  // contains the substring "male"), or every Male query ties with the adjacent
  // Female radio and DOM order decides. Underscores/digits count as boundaries so
  // a value like "male" inside "0_eligibilityrules_male" still matches as a word.
  const RE = {};
  const hasWord = (txt, t) => {
    if (!txt) return false;
    let re = RE[t];
    if (!re) re = RE[t] = new RegExp('(^|[^a-z0-9])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([^a-z0-9]|$)');
    return re.test(txt);
  };
  const overlap = (txt) => { if (!txt) return 0; let n = 0; tokens.forEach((t) => { if (hasWord(txt, t)) n++; }); return n / tokens.length; };
  // Section context matches by SUBSTRING (not whole word): the discriminating
  // word is frequently a prefix inside a camelCase id/name ("eligibility" in
  // "eligibilityRules_male"), which a word-boundary test would miss. The section
  // words ("eligibility"/"recommendation") are long and distinctive, so substring
  // matching won't create the male/female-style false ties that the option label
  // must avoid.
  const ctxOverlap = (txt) => { if (!ctxTokens.length || !txt) return 0; let n = 0; ctxTokens.forEach((t) => { if (txt.indexOf(t) >= 0) n++; }); return n / ctxTokens.length; };
  // The section a control lives in is signalled not just by a heading but also by
  // the control's own id/name and its ancestors' ids (Ant names radios
  // "eligibilityRules_male" / "recommendationRules_male"), which is far more
  // reliable than headings alone.
  const sectionHaystack = (e) => {
    const parts = [sectionText(e)];
    if (e.id) parts.push(e.id);
    if (e.name) parts.push(e.name);
    if (e.getAttribute && e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    // Climb ancestors and, at each, pick up its id and the text of a DIRECT
    // heading/title child (card head, a *[class*=title], a <b>/<strong>/<legend>/
    // <hN>). Direct-child only + short cap so we grab the block's own title (e.g.
    // "Eligibility Criteria #1") and never its body — robust to the exact Ant
    // markup so section detection doesn't hinge on one class name.
    let p = e.parentElement, hops = 0;
    while (p && hops < 8) {
      if (p.id) parts.push(p.id);
      let h = null;
      try {
        h = p.querySelector(':scope > .ant-card-head, :scope > [class*="head"], :scope > [class*="title"], :scope > [class*="Title"], :scope > legend, :scope > b, :scope > strong, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > h6');
      } catch (err) { h = null; }
      if (h) { const t = (h.textContent || '').trim(); if (t && t.length <= 80) parts.push(t); }
      p = p.parentElement; hops++;
    }
    return norm(parts.join(' '));
  };

  let best = null, bestScore = -1, bestSection = '';
  els.filter(shown).forEach((e, i) => {
    const sec = sectionText(e);
    // Option label is the dominant signal (weight 1.0); the section context is a
    // bounded tiebreak (weight 0.5 < 1.0) so it can never override which OPTION
    // is chosen — only which of two equally-matching sections it lives in.
    const score = overlap(labelText(e)) + 0.5 * ctxOverlap(sectionHaystack(e)) + i * 0.0001;
    if (score > bestScore) { bestScore = score; best = e; bestSection = sec; }
  });
  if (!best || bestScore <= 0) return null;

  const checked = !!best.checked
    || best.getAttribute('aria-checked') === 'true'
    || !!(wrapperOf(best) && wrapperOf(best).className &&
          /(-|\b)(checked|selected|active)\b/.test(wrapperOf(best).className));
  const target = wrapperOf(best) || best;
  // A clean, human display name (the visible wrapper text, else aria-label/value)
  // rather than the concatenated match signals.
  const w = wrapperOf(best);
  const displayName = norm((w && w.textContent) || best.getAttribute('aria-label') || best.value || '');
  document.querySelectorAll('[data-bg-radio]').forEach((n) => n.removeAttribute('data-bg-radio'));
  target.setAttribute('data-bg-radio', '1');
  return { selector: '[data-bg-radio="1"]', checked, name: displayName, section: bestSection, score: bestScore };
}
""".replace("__SECTION_JS", _SECTION_HEADING_JS)


# JS: resolve a checkbox by its label text — mirror of _FIND_RADIO_JS. Ant/MUI
# checkboxes are a hidden (`opacity:0`) `<input type=checkbox>` inside a styled
# `<label>` wrapper (`.ant-checkbox-wrapper`), so name-based grounding is
# unreliable and a "Select X checkbox" step wrongly falls to the dropdown
# resolver. Returns the clickable wrapper/label plus the current checked state so
# the caller can toggle idempotently.
_FIND_CHECKBOX_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 1);
  if (!tokens.length) return null;
  const STOP = new Set(['select','check','checkbox','tick','box','option','the','for','on','in','of','to','a','an','choose','click','pick','set','and','with','value','field','uncheck','unselect','deselect','untick','clear']);
  const ctx = norm(args && args.context);
  const ctxTokens = ctx.split(' ')
    .map((t) => t.replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, ''))
    .filter((t) => t.length > 2 && !STOP.has(t) && tokens.indexOf(t) < 0);

  const els = Array.from(document.querySelectorAll('input[type=checkbox], [role=checkbox]'));
  if (!els.length) return null;

  const wrapperOf = (e) => e.closest(
    'label, .ant-checkbox-wrapper, [class*="checkbox-wrapper"], [class*="CheckboxWrapper"],'
    + ' [class*="FormControlLabel"], [class*="form-check"]'
  );
  const shown = (e) => {
    const w = wrapperOf(e) || e;
    const r = w.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(w);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const labelText = (e) => {
    const parts = [];
    const wl = e.closest('label');
    if (wl) parts.push(wl.textContent);
    if (e.id) { const l = document.querySelector('label[for="' + (window.CSS ? CSS.escape(e.id) : e.id) + '"]'); if (l) parts.push(l.textContent); }
    if (e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const lb = e.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach((id) => { const n = document.getElementById(id); if (n) parts.push(n.textContent); });
    const w = wrapperOf(e);
    if (w) parts.push(w.textContent);
    if (e.value) parts.push(e.value);
    return norm(parts.join(' '));
  };
  __SECTION_JS
  // Whole-word match (see the radio resolver): "Food purchase" prefers the exact
  // checkbox over a partial ("Drink purchase" shares "purchase"), and a shared
  // substring can't create a false tie.
  const RE = {};
  const hasWord = (txt, t) => {
    if (!txt) return false;
    let re = RE[t];
    if (!re) re = RE[t] = new RegExp('(^|[^a-z0-9])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([^a-z0-9]|$)');
    return re.test(txt);
  };
  const overlap = (txt) => { if (!txt) return 0; let n = 0; tokens.forEach((t) => { if (hasWord(txt, t)) n++; }); return n / tokens.length; };
  // Substring match for the section context (see the radio resolver) so a word
  // that is only a prefix inside a camelCase id/name still counts.
  const ctxOverlap = (txt) => { if (!ctxTokens.length || !txt) return 0; let n = 0; ctxTokens.forEach((t) => { if (txt.indexOf(t) >= 0) n++; }); return n / ctxTokens.length; };
  const sectionHaystack = (e) => {
    const parts = [sectionText(e)];
    if (e.id) parts.push(e.id);
    if (e.name) parts.push(e.name);
    if (e.getAttribute && e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    let p = e.parentElement, hops = 0;
    while (p && hops < 8) {
      if (p.id) parts.push(p.id);
      let h = null;
      try {
        h = p.querySelector(':scope > .ant-card-head, :scope > [class*="head"], :scope > [class*="title"], :scope > [class*="Title"], :scope > legend, :scope > b, :scope > strong, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > h5, :scope > h6');
      } catch (err) { h = null; }
      if (h) { const t = (h.textContent || '').trim(); if (t && t.length <= 80) parts.push(t); }
      p = p.parentElement; hops++;
    }
    return norm(parts.join(' '));
  };

  let best = null, bestScore = -1, bestSection = '';
  els.filter(shown).forEach((e, i) => {
    const sec = sectionText(e);
    // Option label dominates (weight 1.0); section context is a bounded tiebreak
    // (0.5) that only decides between equally-matching sections.
    const score = overlap(labelText(e)) + 0.5 * ctxOverlap(sectionHaystack(e)) - i * 0.0001;
    if (score > bestScore) { bestScore = score; best = e; bestSection = sec; }
  });
  if (!best || bestScore <= 0) return null;

  const checked = !!best.checked
    || best.getAttribute('aria-checked') === 'true'
    || !!(wrapperOf(best) && wrapperOf(best).className &&
          /(-|\b)(checked|selected|active)\b/.test(wrapperOf(best).className));
  const target = wrapperOf(best) || best;
  const w = wrapperOf(best);
  const displayName = norm((w && w.textContent) || best.getAttribute('aria-label') || best.value || '');
  document.querySelectorAll('[data-bg-checkbox]').forEach((n) => n.removeAttribute('data-bg-checkbox'));
  target.setAttribute('data-bg-checkbox', '1');
  return { selector: '[data-bg-checkbox="1"]', checked, name: displayName, section: bestSection, score: bestScore };
}
""".replace("__SECTION_JS", _SECTION_HEADING_JS)


# JS: resolve the start/end input of a date **range** picker. These inputs are
# typically nameless (no id/label/aria) and only distinguishable by a
# `date-range="start|end"` attribute, a "Start date"/"End date" placeholder, or
# their position inside `.ant-picker-range` — so name-based grounding can send a
# "type into Start date" step to the wrong element. Deterministic by construction.
_FIND_DATE_RANGE_JS = r"""
(args) => {
  // Nearest form-item-ish ancestor that actually CONTAINS a label — see the
  // note in _FIND_SELECT_TRIGGER_JS (Ant's nested control wrapper otherwise
  // swallows closest() and the label disambiguation returns nothing).
  const __bgField = (e, sel) => {
    let p = e.parentElement, hops = 0;
    while (p && hops < 15) {
      if (p.matches(sel) && p.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])')) return p;
      p = p.parentElement; hops++;
    }
    return e.closest(sel);
  };
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const which = norm(args && args.which);          // "start" | "end"
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 2);
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };

  // Candidate range inputs: explicit [date-range] first, else inputs inside an
  // .ant-picker-range (tagged with their DOM position: 0=start, 1=end).
  let cands = Array.from(document.querySelectorAll('input[date-range]')).filter(visible);
  if (!cands.length) {
    document.querySelectorAll('.ant-picker-range').forEach((p) => {
      Array.from(p.querySelectorAll('input')).filter(visible).forEach((e, i) => {
        e.__bgRangePos = i; cands.push(e);
      });
    });
  }
  if (!cands.length) return null;

  const side = (e) => {
    const dr = norm(e.getAttribute('date-range'));
    if (dr === 'start' || dr === 'begin' || dr === 'from') return 'start';
    if (dr === 'end' || dr === 'to' || dr === 'until') return 'end';
    const ph = norm(e.getAttribute('placeholder'));
    if (ph.includes('start') || ph.includes('from') || ph.includes('begin')) return 'start';
    if (ph.includes('end') || ph.includes('to') || ph.includes('until')) return 'end';
    if (e.__bgRangePos === 0) return 'start';
    if (e.__bgRangePos === 1) return 'end';
    return null;
  };

  let matches = cands.filter((e) => side(e) === which);
  if (!matches.length) return null;

  // Multiple range pickers on one page: pick the one whose form-item label best
  // overlaps the phrase (e.g. "... into the Visibility Period start date").
  if (matches.length > 1 && tokens.length) {
    const labelText = (e) => {
      const fi = __bgField(e, '.ant-form-item, .ant-row, [class*="form-item"], [class*="field"]');
      const l = fi && fi.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])');
      return norm(l ? l.textContent : '');
    };
    const overlap = (txt) => { let n = 0; tokens.forEach((t) => { if (txt.includes(t)) n++; }); return n; };
    matches.sort((a, b) => overlap(labelText(b)) - overlap(labelText(a)));
  }

  const best = matches[0];
  document.querySelectorAll('[data-bg-daterange]').forEach((n) => n.removeAttribute('data-bg-daterange'));
  best.setAttribute('data-bg-daterange', '1');
  return { selector: '[data-bg-daterange="1"]', which };
}
"""


# JS: resolve a file `<input type=file>` for an upload step by its surrounding
# context. These inputs are almost always hidden (Ant/MUI upload widgets wrap a
# `display:none` input behind a styled button), so the a11y tree and the visible
# input fallback can't reach them. Scores by form-item label, the nearest section
# heading (so repeated labels like "Album View" under "Awarded" vs "Upcoming" are
# distinguishable), and id/name/testid (camelCase + kebab split into words).
_FIND_FILE_INPUT_JS = r"""
(args) => {
  // Nearest form-item-ish ancestor that actually CONTAINS a label — see the
  // note in _FIND_SELECT_TRIGGER_JS (Ant's nested control wrapper otherwise
  // swallows closest() and the label/testid context returns nothing).
  const __bgField = (e, sel) => {
    let p = e.parentElement, hops = 0;
    while (p && hops < 15) {
      if (p.matches(sel) && p.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"])')) return p;
      p = p.parentElement; hops++;
    }
    return e.closest(sel);
  };
  const norm = (s) => (s || '').replace(/([a-z0-9])([A-Z])/g, '$1 $2')
                                .replace(/[-_]+/g, ' ')
                                .replace(/\s+/g, ' ').trim().toLowerCase();
  const phrase = norm(args && args.phrase);
  const tokens = phrase.split(' ').filter((t) => t.length > 1);
  if (!tokens.length) return null;

  const els = Array.from(document.querySelectorAll('input[type=file]'));
  if (!els.length) return null;

  // Nearest section heading preceding the element in document order.
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]'));
  const sectionText = (el) => {
    let best = '';
    for (const h of headings) {
      if (el.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_PRECEDING) best = h.textContent;
      else break;
    }
    return norm(best);
  };

  const contextText = (e) => {
    const parts = [];
    if (e.id) {
      const l = document.querySelector('label[for="' + (window.CSS ? CSS.escape(e.id) : e.id) + '"]');
      if (l) parts.push(l.textContent);
    }
    if (e.getAttribute('aria-label')) parts.push(e.getAttribute('aria-label'));
    const fi = __bgField(e, '.ant-form-item, [class*="form-item"], [class*="field"], [class*="uploader"], [class*="upload"]');
    if (fi) {
      const l = fi.querySelector('label:not(.ant-checkbox-wrapper):not(.ant-radio-wrapper):not([class*="checkbox"]):not([class*="radio"]), .ant-form-item-label, [class*="label"]:not([class*="ql-"]):not([class*="picker"]):not([class*="tox-"]):not([class*="ck-"]):not([class*="checkbox"]):not([class*="radio"]):not([class*="select"]), [title]:not([class*="ql-"]):not([class*="picker"]):not([class*="checkbox"]):not([class*="radio"])');
      if (l) parts.push(l.getAttribute('title') || l.textContent);
      if (fi.getAttribute('data-testid')) parts.push(fi.getAttribute('data-testid'));
    }
    if (e.name) parts.push(e.name);
    if (e.id) parts.push(e.id);
    if (e.getAttribute('data-testid')) parts.push(e.getAttribute('data-testid'));
    parts.push(sectionText(e));
    return norm(parts.join(' '));
  };

  const overlap = (txt) => { if (!txt) return 0; let n = 0; tokens.forEach((t) => { if (txt.includes(t)) n++; }); return n / tokens.length; };

  let best = null, bestScore = -1, bestTxt = '', tie = false;
  els.forEach((e, i) => {
    const txt = contextText(e);
    const score = overlap(txt) + (els.length - i) * 0.0001;   // stable DOM tie-break
    if (score > bestScore + 1e-9) { bestScore = score; best = e; bestTxt = txt; tie = false; }
    else if (Math.abs(score - bestScore) <= 1e-4) { tie = true; }
  });
  if (!best || bestScore <= 0) return null;

  document.querySelectorAll('[data-bg-file]').forEach((n) => n.removeAttribute('data-bg-file'));
  best.setAttribute('data-bg-file', '1');
  return { selector: '[data-bg-file="1"]', label: bestTxt, score: bestScore, tie };
}
"""


# JS: click any interactive element by accessible name (button/link/menuitem/
# tab/...). Exact → case-insensitive → substring; collapses nested matches to the
# outermost interactive ancestor and prefers button/link roles. Marks the winner.
_FIND_CLICKABLE_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const want = norm(args && args.text);
  const exact = !!(args && args.exact);
  if (!want) return null;
  // Also try the text with a trailing widget noun removed, so "Badges menu"
  // matches a nav item named "Badges" (the widget word describes the control).
  const stripped = want.replace(/\s+(menu\s*item|menuitem|menu|button|link|tab|option|item|field)$/i, '').trim();
  const wants = stripped && stripped !== want ? [want, stripped] : [want];
  const SEL = 'button, [role="button"], a, [role="link"], [role="menuitem"], [role="tab"],'
            + ' input[type="submit"], input[type="button"], summary, [onclick]';
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const nameOf = (e) => {
    const al = e.getAttribute && e.getAttribute('aria-label');
    if (al) return norm(al);
    if (e.tagName === 'INPUT') return norm(e.value);
    const t = norm(e.textContent);
    if (t) return t;
    return norm(e.getAttribute && e.getAttribute('title'));
  };
  const els = Array.from(document.querySelectorAll(SEL)).filter(visible);
  let matches = [];
  for (const w of wants) {
    const wl = w.toLowerCase();
    matches = els.filter((e) => nameOf(e) === w);
    if (!matches.length && !exact) matches = els.filter((e) => nameOf(e).toLowerCase() === wl);
    if (!matches.length && !exact) matches = els.filter((e) => nameOf(e).toLowerCase().includes(wl));
    if (matches.length) break;
  }
  if (!matches.length) return null;
  // Outermost interactive ancestor (drop a matched element nested in another).
  matches = matches.filter((e) => !matches.some((o) => o !== e && o.contains(e)));
  const rank = (e) => {
    const tag = e.tagName.toLowerCase();
    const role = (e.getAttribute && e.getAttribute('role')) || '';
    if (tag === 'button' || role === 'button' || e.type === 'submit' || e.type === 'button') return 3;
    if (tag === 'a' || role === 'link') return 2;
    return 1;
  };
  matches.sort((a, b) => rank(b) - rank(a));
  const best = matches[0];
  document.querySelectorAll('[data-bg-click]').forEach((n) => n.removeAttribute('data-bg-click'));
  best.setAttribute('data-bg-click', '1');
  return { selector: '[data-bg-click="1"]', count: matches.length, name: nameOf(best), tag: best.tagName };
}
"""


# JS: resolve a clickable INSIDE the topmost open dialog/modal by name. When a
# blocking modal is open (e.g. an Ant confirm "Submit Badge?"), a button named
# "Submit" also exists on the page behind it — the page copy is covered by the
# modal mask, so clicking it hangs. This scopes the search to the dialog and
# splits off an "... on <title> dialog" scope tail so the button label matches.
_FIND_DIALOG_CLICKABLE_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const want = norm(args && args.text);
  const exact = !!(args && args.exact);
  if (!want) return null;
  const visible = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const s = window.getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };

  // Topmost open dialog: role=dialog / native <dialog> / common modal classes,
  // visible only, ranked by effective z-index then DOM order (last wins).
  const DIALOG = "[role='dialog'],[role='alertdialog'],dialog[open],"
               + ".ant-modal,.ant-modal-confirm,.MuiDialog-container,"
               + "[class*='modal'][class*='show'],[class*='Modal'][class*='open']";
  let dialogs = Array.from(document.querySelectorAll(DIALOG)).filter(visible);
  if (!dialogs.length) return null;
  const zOf = (e) => { let n = e, m = 0; while (n) { const v = parseInt(window.getComputedStyle(n).zIndex); if (!isNaN(v)) m = Math.max(m, v); n = n.parentElement; } return m; };
  dialogs.sort((a, b) => (zOf(a) - zOf(b)) || ((a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1));
  const dialog = dialogs[dialogs.length - 1];

  // The button label is the part before a scope preposition ("Submit button on
  // Submit Badge? dialog" -> "Submit button"); strip a trailing widget noun.
  let main = want.split(/\s+(?:on|in|within|from|of)\s+/i)[0]
                 .replace(/\s+(button|link|tab|option|item|menu\s*item|menuitem)$/i, '').trim();
  const wants = [main, want].filter((v, i, a) => v && a.indexOf(v) === i);

  const SEL = 'button, [role="button"], a, [role="link"], [role="menuitem"], [role="tab"],'
            + ' input[type="submit"], input[type="button"], summary, [onclick]';
  const nameOf = (e) => {
    const al = e.getAttribute && e.getAttribute('aria-label');
    if (al) return norm(al);
    if (e.tagName === 'INPUT') return norm(e.value);
    const t = norm(e.textContent);
    if (t) return t;
    return norm(e.getAttribute && e.getAttribute('title'));
  };
  const els = Array.from(dialog.querySelectorAll(SEL)).filter(visible);
  if (!els.length) return null;

  let matches = [];
  for (const w of wants) {
    const wl = w.toLowerCase();
    matches = els.filter((e) => nameOf(e) === w);
    if (!matches.length && !exact) matches = els.filter((e) => nameOf(e).toLowerCase() === wl);
    if (!matches.length && !exact) matches = els.filter((e) => nameOf(e).toLowerCase().includes(wl));
    if (matches.length) break;
  }
  if (!matches.length) return null;
  matches = matches.filter((e) => !matches.some((o) => o !== e && o.contains(e)));
  const best = matches[0];
  document.querySelectorAll('[data-bg-dialogclick]').forEach((n) => n.removeAttribute('data-bg-dialogclick'));
  best.setAttribute('data-bg-dialogclick', '1');
  return { selector: '[data-bg-dialogclick="1"]', name: nameOf(best), count: matches.length };
}
"""


# JS: click a link by its (possibly dynamic) text. Exact → case-insensitive →
# substring. Marks the match with a temporary attribute and returns its selector.
_FIND_LINK_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const want = norm(args && args.text);
  const wantL = want.toLowerCase();
  const exact = !!(args && args.exact);
  const visible = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const links = Array.from(document.querySelectorAll('a, [role="link"]')).filter(visible);
  if (!want || !links.length) return null;
  let match = links.find((a) => norm(a.textContent) === want);
  if (!match && !exact) match = links.find((a) => norm(a.textContent).toLowerCase() === wantL);
  if (!match && !exact) match = links.find((a) => norm(a.textContent).toLowerCase().includes(wantL));
  if (!match) return null;
  document.querySelectorAll('[data-bg-link]').forEach((n) => n.removeAttribute('data-bg-link'));
  match.setAttribute('data-bg-link', '1');
  return { selector: '[data-bg-link="1"]', text: norm(match.textContent) };
}
"""


# JS: click an element in a table cell, addressed by column header + row
# (1-based index, -1 = last, or a {column: value} match). Handles native
# <table>, Ant Design .ant-table (header/body split), and ARIA grids. Returns a
# selector for the clickable child of the cell (a/button/input) or the cell.
_FIND_TABLE_CELL_JS = r"""
(args) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const key = (s) => norm(s).toLowerCase();
  const colWant = key(args && args.column);
  const rowIndex = (args && args.rowIndex != null) ? args.rowIndex : null;
  const rowMatch = (args && args.rowMatch) || null;
  const preferClickable = !(args && args.preferClickable === false);

  const findHeaderIdx = (headers) => {
    let i = headers.findIndex((h) => key(h) === colWant);
    if (i < 0) i = headers.findIndex((h) => colWant && (key(h).includes(colWant) || colWant.includes(key(h))));
    return i;
  };

  // Build [{headers:[txt], rows:[[tdEl,...]]}] across table flavours.
  const tables = [];
  document.querySelectorAll('.ant-table').forEach((t) => {
    const headers = Array.from(t.querySelectorAll('.ant-table-thead th')).map((th) => norm(th.textContent));
    if (!headers.length) return;
    const rows = [];
    t.querySelectorAll('.ant-table-tbody tr').forEach((tr) => {
      if (tr.getAttribute('aria-hidden') === 'true') return;
      const cells = Array.from(tr.querySelectorAll('td'));
      if (cells.length) rows.push(cells);
    });
    tables.push({ headers, rows });
    t.querySelectorAll('table').forEach((x) => x.setAttribute('data-bg-seen', '1'));
  });
  document.querySelectorAll('table').forEach((t) => {
    if (t.getAttribute('data-bg-seen') === '1' || t.closest('.ant-table')) return;
    let headers = Array.from(t.querySelectorAll('thead th')).map((th) => norm(th.textContent));
    if (!headers.length) { const fr = t.querySelector('tr'); if (fr) headers = Array.from(fr.querySelectorAll('th,td')).map((c) => norm(c.textContent)); }
    if (!headers.length) return;
    const body = t.querySelectorAll('tbody tr');
    const trs = body.length ? body : t.querySelectorAll('tr');
    const rows = [];
    trs.forEach((tr) => { const cells = Array.from(tr.querySelectorAll('td')); if (cells.length) rows.push(cells); });
    tables.push({ headers, rows });
  });
  document.querySelectorAll('[data-bg-seen]').forEach((n) => n.removeAttribute('data-bg-seen'));
  document.querySelectorAll('[role="table"], [role="grid"]').forEach((t) => {
    if (t.tagName === 'TABLE' || t.closest('.ant-table')) return;
    const headers = Array.from(t.querySelectorAll('[role="columnheader"]')).map((c) => norm(c.textContent));
    if (!headers.length) return;
    const rows = [];
    t.querySelectorAll('[role="row"]').forEach((r) => {
      const cells = Array.from(r.querySelectorAll('[role="gridcell"], [role="cell"]'));
      if (cells.length) rows.push(cells);
    });
    tables.push({ headers, rows });
  });

  // Pick the first table that has the column and a usable row.
  for (const tbl of tables) {
    const ci = findHeaderIdx(tbl.headers);
    if (ci < 0 || !tbl.rows.length) continue;

    let row = null;
    if (rowMatch) {
      row = tbl.rows.find((cells) => Object.keys(rowMatch).every((k) => {
        let mi = tbl.headers.findIndex((h) => key(h) === key(k));
        if (mi < 0) mi = tbl.headers.findIndex((h) => key(h).includes(key(k)) || key(k).includes(key(h)));
        if (mi < 0 || !cells[mi]) return false;
        return norm(cells[mi].textContent).toLowerCase().includes(key(rowMatch[k]));
      })) || null;
    } else {
      let idx = (rowIndex == null) ? 1 : rowIndex;
      if (idx < 0) idx = tbl.rows.length + idx + 1; // -1 => last
      if (idx >= 1 && idx <= tbl.rows.length) row = tbl.rows[idx - 1];
    }
    if (!row || !row[ci]) continue;

    const cell = row[ci];
    let target = cell;
    if (preferClickable) {
      const click = cell.querySelector('a, button, [role="link"], [role="button"], input, [onclick], [tabindex]');
      if (click) target = click;
    }
    document.querySelectorAll('[data-bg-cell]').forEach((n) => n.removeAttribute('data-bg-cell'));
    target.setAttribute('data-bg-cell', '1');
    return { selector: '[data-bg-cell="1"]', text: norm(target.textContent), tag: target.tagName };
  }
  return null;
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

    # An input that belongs to a date/time picker widget commits typed text only
    # on a keystroke (Enter), and keeps "active editing" on one field until then.
    # Detected generically across libraries (Ant `.ant-picker`, MUI pickers, and
    # the `date-range` attribute) so a range picker's start/end don't collide.
    _PICKER_PROBE_JS = r"""
    (el) => {
      if (!el) return false;
      if (el.hasAttribute('date-range')) return true;
      return !!el.closest(
        '.ant-picker, .ant-picker-range,'
        + '[class*="DatePicker"],[class*="datepicker"],[class*="date-picker"],'
        + '[class*="TimePicker"],[class*="timepicker"],[class*="time-picker"],'
        + '[class*="MuiPickers"],[class*="Pickers"]'
      );
    }
    """

    async def _is_picker_input(self, locator) -> bool:
        try:
            return bool(await locator.evaluate(self._PICKER_PROBE_JS))
        except Exception:  # noqa: BLE001 — probe is best-effort
            return False

    async def _do_type(self, plan: ActionPlan, locator, timeout: int) -> None:
        value = plan.input_value or ""
        # Date/time picker inputs (e.g. Ant RangePicker) need an explicit
        # activate + commit: click to make this field the active editor, fill it,
        # then press Enter to commit — otherwise the widget keeps routing text to
        # the previously-active field (both range values land in "start").
        if await self._is_picker_input(locator):
            try:
                await locator.click(timeout=timeout)
            except Exception:  # noqa: BLE001 — focus via fill() is the fallback
                pass
            await locator.fill(value, timeout=timeout)
            try:
                await locator.press("Enter", timeout=timeout)
            except Exception:  # noqa: BLE001 — value is already set; commit is best-effort
                pass
            return
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
        # Multi-select support: a tags widget takes several values in one step,
        # written comma-separated ("GaqAccepted, Aerobic, Strength"). Only split
        # for an actual multi-select so a single value that legitimately contains
        # a comma is left intact on ordinary selects.
        values = await self._split_multi_values(trigger, value)
        if len(values) > 1:
            missed = []
            for v in values:
                # Don't self-correct across other dropdowns for each value: we
                # already know THIS multi-select is the target, and probing the
                # rest per value is what made the step take ~44s and left a stray
                # popup open in another section.
                if not await self._select_single(trigger, v, timeout, probe_others=False):
                    missed.append(v)
            if missed and len(missed) == len(values):
                raise ValueError(
                    f"could not add any of {values!r} to the multi-select dropdown"
                )
            if missed:
                logger.warning("multi-select: could not add %r (added the rest)", missed)
            return

        if await self._select_single(trigger, values[0], timeout):
            return
        raise ValueError(
            f"could not find a dropdown option matching {value!r} after opening "
            f"the combobox (tried role=option/menuitem, .ant-select-item-option "
            f"by title/text, open-popup text/title, the aria-controls listbox, "
            f"and every other combobox on the page)"
        )

    async def _split_multi_values(self, trigger, value: str) -> list:
        """Split a comma-joined value into items, but only for a multi-select.

        A tags widget (``ant-select-multiple``) accepts several values in one
        step ("GaqAccepted, Aerobic"). For an ordinary single select a comma is
        part of the value and must not be split.
        """
        if not value or "," not in value:
            return [value]
        try:
            is_multi = await trigger.evaluate(
                "el => { const r = (el.closest && el.closest('.ant-select')) || el;"
                " return !!(r.classList && r.classList.contains('ant-select-multiple'))"
                " || (r.getAttribute && r.getAttribute('aria-multiselectable') === 'true')"
                " || !!(r.querySelector && r.querySelector('.ant-select-multiple')); }"
            )
        except Exception:  # noqa: BLE001
            is_multi = False
        if not is_multi:
            return [value]
        parts = [v.strip() for v in value.split(",") if v.strip()]
        return parts or [value]

    async def _select_single(self, trigger, value: str, timeout: int,
                             probe_others: bool = True) -> bool:
        """Commit one ``value`` into a combobox, self-correcting the trigger.

        Tries the resolved trigger first; if it does not actually offer the value
        (a group heading like "Eligibility Tags" over several selects, so
        label-scoring picked the wrong one) it falls back to the OTHER visible
        comboboxes and commits to whichever contains the value — the value is
        ground truth. Returns True when an option was committed. Any stray
        selection left on a merely-probed candidate is undone.

        ``probe_others=False`` restricts the attempt to the given trigger (used
        when adding several values to one known multi-select).
        """
        candidates = [trigger]
        if probe_others:
            candidates += await self._other_select_triggers(trigger)
        before = [await self._selected_texts(c) for c in candidates]

        picked = -1
        for i, cand in enumerate(candidates):
            try:
                if await self._try_pick_option(cand, value, timeout):
                    picked = i
                    break
            except Exception:  # noqa: BLE001 — try the next candidate
                pass

        # Some widgets auto-select the active option when the field blurs, so
        # probing a wrong candidate can leave a stray selection. Undo any NEW
        # selection in every combobox we did not commit to.
        for i, cand in enumerate(candidates):
            if i == picked:
                continue
            try:
                await self._remove_new_selections(cand, before[i])
            except Exception:  # noqa: BLE001 — cleanup is best-effort
                pass
        return picked >= 0

    async def _selected_texts(self, trigger) -> list:
        """Titles/labels of the items currently selected in a combobox (Ant tags).

        Climbs to the ``.ant-select`` widget root first: grounding often resolves a
        select to its INNER ``<input role=combobox>`` (accessible name), and the
        selection items are siblings/ancestors of that input, not descendants — so
        querying the input alone returns nothing and every commit check
        false-negatives (the "ran twice + 28s probe" symptom).
        """
        try:
            return await trigger.evaluate(
                "el => { const root = (el.closest && el.closest('.ant-select')) || el;"
                " return Array.from(root.querySelectorAll('.ant-select-selection-item'))"
                ".map(n => (n.getAttribute('title') || n.textContent || '').trim()); }"
            )
        except Exception:  # noqa: BLE001
            return []

    async def _is_ant_select(self, trigger) -> bool:
        """Whether the trigger is an Ant ``.ant-select`` (selection is a tag/item).

        Only these reliably reflect a committed choice as a
        ``.ant-select-selection-item``, so only for these can we *verify* that a
        click actually took — see ``_value_committed``.
        """
        try:
            return bool(await trigger.evaluate(
                "el => el.matches('.ant-select') || !!el.querySelector('.ant-select')"
                " || !!el.closest('.ant-select')"
            ))
        except Exception:  # noqa: BLE001
            return False

    async def _value_committed(self, trigger, value: str) -> bool:
        """True when ``value`` now shows as a selected item in an Ant select.

        Guards the "click landed but nothing was selected" failure: some widgets
        (virtualised / portalled lists) accept the option click as a DOM event
        yet never commit it, leaving the value merely typed. Comparing against the
        rendered selection items catches that so the caller can retry via Enter.

        The match is lenient (equal, or either string contains the other, after
        whitespace/case normalisation): a real widget may render the committed
        choice with extra affixes (counts, icons, a truncated label), and a
        *strict* equality check there false-negatives — which used to send a
        correctly-selected single-select into the slow other-combobox probe and a
        redundant Enter press ("ran twice"). Lenient matching avoids that.
        """
        want = " ".join((value or "").split()).strip().lower()
        if not want:
            return False
        for t in await self._selected_texts(trigger):
            got = " ".join((t or "").split()).strip().lower()
            if got and (got == want or want in got or got in want):
                return True
        return False

    async def _dropdown_open(self) -> bool:
        """Whether any option popup is currently open and visible on the page."""
        try:
            return bool(await self._page.evaluate(
                r"""() => {
                  const sel = '.ant-select-dropdown:not(.ant-select-dropdown-hidden),'
                    + ' [role="listbox"]:not([aria-hidden="true"]), [role="menu"]';
                  return Array.from(document.querySelectorAll(sel)).some((o) => {
                    const r = o.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  });
                }"""
            ))
        except Exception:  # noqa: BLE001
            return False

    async def _remove_new_selections(self, trigger, before: list) -> None:
        """Deselect items that appeared in ``trigger`` since ``before`` was taken.

        Clicks each new tag's remove (×) control so a wrong candidate we merely
        probed is left exactly as we found it. Bounded and best-effort.
        """
        from collections import Counter

        for _ in range(6):
            cur = await self._selected_texts(trigger)
            new_items = list((Counter(cur) - Counter(before)).elements())
            if not new_items:
                return
            target = new_items[0]
            esc = target.replace("\\", "\\\\").replace('"', '\\"')
            remove = trigger.locator(
                f'.ant-select-selection-item[title="{esc}"] .ant-select-selection-item-remove'
            ).first
            if await remove.count() == 0:
                remove = trigger.locator(
                    ".ant-select-selection-item", has_text=target
                ).locator(".ant-select-selection-item-remove").first
            if await remove.count() == 0:
                return
            try:
                await remove.click(timeout=1000)
            except Exception:  # noqa: BLE001
                return

    async def _try_pick_option(self, trigger, value: str, timeout: int) -> bool:
        """Open one combobox, filter by typing, and click the matching option.

        Returns True when an option was clicked, False when this combobox does
        not offer ``value`` (leaving it cleared + closed so the next candidate
        starts from a clean page). Never raises for a normal "not found".
        """
        probe = min(timeout, 3000)
        try:
            await self._open_combobox(trigger, timeout)
        except Exception:  # noqa: BLE001 — an un-openable trigger simply doesn't match
            return False

        # Searchable comboboxes (Ant `showSearch`, MUI Autocomplete, react-select)
        # render a *filtered / virtualized* option list — the target row is often
        # not in the DOM until the user types. Type the value into the trigger's
        # own editable search box. No-op for non-search selects (readonly input).
        search = None
        typed_filter = False
        try:
            search = trigger.locator(
                'input.ant-select-selection-search-input, input[role="combobox"], '
                'input[type="search"], input:not([type="hidden"]):not([readonly])'
            ).first
            if await search.count() > 0 and await search.is_editable(timeout=500):
                await search.fill(value, timeout=min(timeout, 2000))
                await self._page.wait_for_timeout(200)
                typed_filter = True
        except Exception:  # noqa: BLE001 — filtering is an optimisation, not required
            search = None

        opened = self._page.locator(
            '[role="option"], [role="menuitem"], .ant-select-item-option, '
            '[role="listbox"], [role="menu"], .ant-select-dropdown'
        )
        try:
            await opened.first.wait_for(state="visible", timeout=probe)
        except Exception:  # noqa: BLE001 — proceed; the attempts still guard themselves
            pass

        esc = value.replace("\\", "\\\\").replace('"', '\\"')
        attempts: list = [
            self._page.get_by_role("option", name=value, exact=True),
            self._page.get_by_role("option", name=value),
            self._page.get_by_role("menuitem", name=value, exact=True),
            self._page.get_by_role("menuitem", name=value),
            self._page.locator(f'.ant-select-item-option[title="{esc}"]'),
            self._page.locator(".ant-select-item-option", has_text=value),
        ]
        popup = self._page.locator(
            '[role="listbox"], [role="menu"], .ant-select-dropdown, '
            '[class*="dropdown"], [class*="menu"], [class*="popover"], [class*="popup"]'
        )
        attempts += [popup.get_by_text(value, exact=True), popup.get_by_title(value, exact=True)]
        container = await self._owned_listbox(trigger)
        if container is not None:
            attempts += [
                container.get_by_text(value, exact=True),
                container.get_by_title(value, exact=True),
                container.get_by_text(value),
            ]

        # For Ant selects the committed choice renders as a selection item, so we
        # can confirm the click actually took. For other widgets we can't verify
        # reliably, so a dispatched click counts as success (legacy behaviour).
        verify = await self._is_ant_select(trigger)
        before_sel = await self._selected_texts(trigger) if verify else []
        for option in attempts:
            try:
                if await option.count() == 0:
                    continue
                await option.first.click(timeout=probe)
                if not verify:
                    logger.debug("combobox pick: clicked option %r", value)
                    return True
                await self._page.wait_for_timeout(120)
                if await self._value_committed(trigger, value):
                    logger.debug("combobox pick: clicked + committed %r", value)
                    return True
                # A single-select replaces its display and closes on commit; if the
                # selection changed and the popup closed, the click took even when
                # the rendered label doesn't string-match the value. This keeps a
                # working single-select on the fast path (no Enter, no probing).
                after_sel = await self._selected_texts(trigger)
                if after_sel != before_sel and not await self._dropdown_open():
                    logger.debug("combobox pick: selection changed + popup closed for %r", value)
                    return True
                # Click was dispatched but the widget did not commit it — keep
                # trying the remaining option shapes, then the Enter fallback.
                logger.debug("combobox pick: click on %r did not commit; retrying", value)
            except Exception:  # noqa: BLE001 — try the next option shape
                continue

        # Enter-to-commit fallback. After typing to filter, Ant (and most
        # searchable selects) highlight the single matching option; a click can
        # still miss it in a virtualised/portalled list, leaving the value merely
        # TYPED but never committed as a selected tag (the exact symptom: "value
        # entered but item not selected"). Only press Enter when we actually typed
        # a filter AND the filtered list shows exactly one option matching the
        # value, so we never commit an unrelated highlighted row.
        if typed_filter:
            try:
                match = await self._page.evaluate(
                    r"""(v) => {
                      const norm = (s) => (s || '').replace(/\s+/g,' ').trim().toLowerCase();
                      const want = norm(v);
                      const opts = Array.from(document.querySelectorAll(
                        '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option, '
                        + '[role="listbox"]:not([aria-hidden="true"]) [role="option"]'
                      )).filter((o) => {
                        const r = o.getBoundingClientRect();
                        return r.width > 0 && r.height > 0
                          && !o.className.includes('ant-select-item-option-disabled')
                          && o.getAttribute('aria-disabled') !== 'true';
                      });
                      if (!opts.length) return false;
                      const texts = opts.map((o) => norm(o.getAttribute('title') || o.textContent));
                      const exact = texts.filter((t) => t === want);
                      // Single exact match, or a single option that clearly contains it.
                      if (exact.length === 1) return true;
                      const contains = texts.filter((t) => t.includes(want));
                      return opts.length === 1 && contains.length === 1;
                    }""",
                    value,
                )
                if match:
                    await self._page.keyboard.press("Enter")
                    await self._page.wait_for_timeout(150)
                    if await self._value_committed(trigger, value):
                        logger.debug("combobox pick: committed %r via Enter", value)
                        return True
            except Exception:  # noqa: BLE001 — Enter fallback is best-effort
                pass

        # No match here — reset this combobox (clear the typed filter, close the
        # popup) so a following candidate isn't confused by a stale open list.
        try:
            if search is not None and await search.count() > 0:
                await search.fill("", timeout=500)
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            pass
        return False

    async def _other_select_triggers(self, exclude_trigger) -> list:
        """Visible combobox triggers other than the already-tried one.

        Tags each with ``data-bg-select-alt`` and returns their locators (DOM
        order, capped). Used to self-correct when the scored trigger did not
        offer the value — the right select is found by which one actually has it.
        """
        try:
            n = await self._page.evaluate(r"""() => {
              const SEL='select, [role="combobox"], .ant-select, .MuiSelect-select, [class*="select__control"]';
              let els=Array.from(document.querySelectorAll(SEL))
                .filter(e=>!e.matches('.ant-select-selection-search-input'));
              els=els.filter(e=>!els.some(o=>o!==e&&o.contains(e)));
              const vis=(e)=>{const r=e.getBoundingClientRect();if(r.width<=0||r.height<=0)return false;
                const s=window.getComputedStyle(e);return s.visibility!=='hidden'&&s.display!=='none';};
              els=els.filter(vis).filter(e=>!e.matches('[data-bg-select="1"]')
                && !e.closest('[data-bg-select="1"]') && !e.querySelector('[data-bg-select="1"]'));
              document.querySelectorAll('[data-bg-select-alt]').forEach(n=>n.removeAttribute('data-bg-select-alt'));
              els.slice(0,6).forEach((e,i)=>e.setAttribute('data-bg-select-alt', String(i)));
              return Math.min(els.length,6);
            }""")
        except Exception:  # noqa: BLE001 — no fallback candidates on failure
            return []
        return [self._page.locator(f'[data-bg-select-alt="{i}"]') for i in range(n or 0)]

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
        await self._set_checkbox(locator, True, timeout)

    async def _do_uncheck(self, plan: ActionPlan, locator, timeout: int) -> None:
        await self._set_checkbox(locator, False, timeout)

    async def _set_checkbox(self, locator, desired: bool, timeout: int) -> None:
        """Toggle a checkbox to ``desired`` idempotently.

        The resolved target is often the styled ``<label>``/wrapper (the real
        `<input>` is hidden and not directly checkable), and the box may already
        be in the wanted state. Read the current state; do nothing if it matches;
        otherwise click the wrapper (which toggles it). Falls back to Playwright's
        native check/uncheck when the element is a plain, directly-usable input.
        """
        state = None
        try:
            state = await locator.evaluate(
                "el => { const inp = el.matches('input') ? el : "
                "el.querySelector('input[type=checkbox], [role=checkbox]');"
                " if (!inp) return null;"
                " return inp.checked !== undefined ? !!inp.checked "
                ": inp.getAttribute('aria-checked') === 'true'; }"
            )
        except Exception:  # noqa: BLE001 — no evaluate() (e.g. test double) / probe failed
            state = None

        if state is not None:
            # Resolved a styled wrapper whose real <input> is hidden — toggle by
            # clicking the wrapper, and only when the state actually differs.
            if bool(state) == bool(desired):
                return  # already in the wanted state — idempotent no-op
            try:
                await locator.click(timeout=timeout)
                return
            except Exception:  # noqa: BLE001 — fall through to native check/uncheck
                pass

        # Plain, directly-checkable input (or state unknown): Playwright's native
        # check/uncheck (itself idempotent).
        if desired:
            await locator.check(timeout=timeout)
        else:
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

    async def find_input(self, target_phrase: str) -> str | None:
        """Resolve a text input / textarea from the DOM and return a selector.

        For ``type`` steps where the field has no accessible name (e.g. a
        ``<textarea>`` whose ``<label for=...>`` points at a missing id). Scores
        every visible, enabled input/textarea by associated label, placeholder,
        name/id, nearby form-item label and section heading against the target
        phrase. Excludes the ant-select search inputs (those are dropdowns).
        """
        result = await self.find_input_ex(target_phrase)
        return result.get("selector") if result else None

    async def find_input_ex(self, target_phrase: str) -> dict | None:
        """Like :meth:`find_input` but returns the full match dict.

        Includes ``section`` (the resolved field's section heading) and
        ``sectioned`` — True when the field shares its visible label with another
        field and a section heading is what set it apart. The section-aware
        pre-resolver uses ``sectioned`` to claim a step ahead of grounding so a
        duplicated field ("Minimum Age" in two sections) isn't mis-resolved.
        """
        result = await self._page.evaluate(_FIND_INPUT_JS, {"phrase": target_phrase or ""})
        if not result:
            return None
        logger.debug(
            "find_input %r -> section=%r sectioned=%s score=%.3f (%s)",
            target_phrase, result.get("section"), result.get("sectioned"),
            result.get("score", 0.0), result.get("selector"),
        )
        return result

    async def find_rich_text(self, target_phrase: str) -> str | None:
        """Resolve a rich-text editor (``contenteditable``) by its form-item label.

        For ``type`` steps whose field is an RTE widget (Quill, TinyMCE,
        ProseMirror, CKEditor, …). These render as a bare ``[contenteditable]``
        div with no ``textbox`` role and no accessible name, so role-based
        grounding can't see them and may mis-match a nearby valued input instead.
        Returns a selector only when the editor's label is a *full* match for the
        phrase (so plain ``<input>`` steps are never hijacked), else ``None`` —
        which leaves non-RTE pages and partial matches to normal grounding.
        """
        result = await self._page.evaluate(_FIND_RICH_TEXT_JS, {"phrase": target_phrase or ""})
        if not result:
            return None
        logger.debug("find_rich_text %r -> %s", target_phrase, result)
        return result.get("selector")

    async def find_date_range_input(self, which: str, target_phrase: str = "") -> str | None:
        """Return a selector for the start/end input of a date **range** picker.

        ``which`` is ``"start"`` or ``"end"``. These inputs are usually nameless
        (Ant ``RangePicker``), so this keys off the ``date-range`` attribute, the
        placeholder, or DOM position inside ``.ant-picker-range`` — deterministic
        where name-based grounding is ambiguous. ``target_phrase`` disambiguates
        when a page has more than one range picker. Returns ``None`` when the page
        has no range picker (so non-picker pages are unaffected).
        """
        result = await self._page.evaluate(
            _FIND_DATE_RANGE_JS, {"which": which or "", "phrase": target_phrase or ""}
        )
        if not result:
            return None
        logger.debug("find_date_range_input %r %r -> %s", which, target_phrase, result)
        return result.get("selector")

    async def find_radio(self, target_phrase: str, context: str = "") -> dict | None:
        """Resolve a radio option by label text. Returns ``{selector, checked,

        name}`` for the clickable wrapper/label (not the hidden input), or
        ``None`` when the page has no radio. Used for both selecting a radio and
        asserting its checked state; works for native, Ant and MUI radios.

        ``context`` is the surrounding instruction (e.g. "… for Eligibility"):
        when two sections share the same option label ("Male"), its non-option
        words are matched against the nearest section heading to pin the right
        section instead of falling to DOM order.
        """
        result = await self._page.evaluate(
            _FIND_RADIO_JS, {"phrase": target_phrase or "", "context": context or ""}
        )
        if not result:
            return None
        logger.debug(
            "find_radio phrase=%r context=%r -> name=%r section=%r score=%.3f (%s)",
            target_phrase, context, result.get("name"), result.get("section"),
            result.get("score", 0.0), result.get("selector"),
        )
        return result

    async def find_checkbox(self, target_phrase: str, context: str = "") -> dict | None:
        """Resolve a checkbox by label text. Returns ``{selector, checked, name}``
        for the clickable wrapper/label (not the hidden input), or ``None`` when
        the page has no checkbox. Works for native, Ant and MUI checkboxes.

        ``context`` (the surrounding instruction) disambiguates sections that
        share an option label — see :meth:`find_radio`.
        """
        result = await self._page.evaluate(
            _FIND_CHECKBOX_JS, {"phrase": target_phrase or "", "context": context or ""}
        )
        logger.debug(
            "find_checkbox phrase=%r context=%r -> %s", target_phrase, context, result,
        )
        if not result:
            return None
        logger.debug("find_checkbox %r -> %s", target_phrase, result)
        return result

    async def find_file_input(self, target_phrase: str) -> str | None:
        """Return a selector for the ``<input type=file>`` matching ``target_phrase``.

        For ``upload`` steps against widgets (Ant/MUI ``Upload``) whose real file
        input is hidden behind a styled button — unreachable via the a11y tree.
        Scores every file input by its form-item label, nearest section heading
        and id/name/testid, so repeated labels (e.g. "Album View" under two
        sections) are disambiguated by naming the section in the phrase. Returns
        ``None`` when the page has no file input (non-upload pages unaffected).
        """
        result = await self._page.evaluate(_FIND_FILE_INPUT_JS, {"phrase": target_phrase or ""})
        if not result:
            return None
        logger.debug("find_file_input %r -> %s", target_phrase, result)
        return result.get("selector")

    async def find_clickable(self, text: str, *, exact: bool = False) -> str | None:
        """Return a selector for a single interactive element named ``text``.

        Searches buttons / links / menuitems / tabs (and other clickable roles)
        by accessible name (aria-label / value / text / title), exact then
        case-insensitive then substring, and collapses nested matches to the
        outermost interactive ancestor. A last-resort click resolver for when the
        a11y snapshot ties (e.g. a button wrapping a same-text span).
        """
        result = await self._page.evaluate(
            _FIND_CLICKABLE_JS, {"text": text or "", "exact": bool(exact)}
        )
        if not result:
            return None
        logger.debug("find_clickable %r -> %s", text, result)
        return result.get("selector")

    async def find_dialog_clickable(self, text: str, *, exact: bool = False) -> str | None:
        """Return a selector for a clickable named ``text`` inside the open dialog.

        When a blocking modal is open, the same button name often also exists on
        the page behind it (covered by the modal mask). Scopes the search to the
        topmost visible dialog and splits off an ``... on <title> dialog`` scope
        tail. Returns ``None`` when no dialog is open (so non-modal flows fall
        through to normal grounding).
        """
        result = await self._page.evaluate(
            _FIND_DIALOG_CLICKABLE_JS, {"text": text or "", "exact": bool(exact)}
        )
        if not result:
            return None
        logger.debug("find_dialog_clickable %r -> %s", text, result)
        return result.get("selector")

    async def find_link(self, text: str, *, exact: bool = False) -> str | None:
        """Return a selector for a visible link whose text matches ``text``.

        Tries exact (normalised) match, then case-insensitive, then substring.
        Useful when the link label is dynamic (e.g. an id pulled from a DB).
        """
        result = await self._page.evaluate(
            _FIND_LINK_JS, {"text": text or "", "exact": bool(exact)}
        )
        if not result:
            return None
        logger.debug("find_link %r -> %s", text, result)
        return result.get("selector")

    async def find_table_cell(
        self, *, column: str, row_index: int | None = None,
        row_match: dict | None = None, prefer_clickable: bool = True,
    ) -> str | None:
        """Return a selector for an element in a table cell.

        Locates the table whose header matches ``column``, selects the row by
        ``row_index`` (1-based; -1 = last) or by ``row_match`` ({column: value}),
        and returns the clickable element inside that cell (a/button/input) when
        ``prefer_clickable``, else the cell itself. Handles native ``<table>``,
        Ant Design ``.ant-table`` (header/body split), and ARIA grids.
        """
        result = await self._page.evaluate(
            _FIND_TABLE_CELL_JS,
            {"column": column or "", "rowIndex": row_index,
             "rowMatch": row_match or None, "preferClickable": bool(prefer_clickable)},
        )
        if not result:
            return None
        logger.debug("find_table_cell col=%r row=%r/%r -> %s", column, row_index, row_match, result)
        return result.get("selector")

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
