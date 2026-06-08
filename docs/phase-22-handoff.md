# Phase 22 — Handoff

Status: Phase 22D + 22E-1 shipped end-to-end. The widget lab runs 7/7
scenarios NL-only against real Chromium with no `selector=`,
`action_type=`, or `input_value=` safety nets.

Use this doc as the entry point when resuming work in a fresh session.
The conversation history is not needed — every relevant file path,
acceptance gate, and queued PR is captured below.

---

## What shipped on `claude/confident-ritchie-jknV6`

### 22D — Tier 1 widget expansion
- Closed vocabulary `ControlKind` (link, radio, checkbox, switch, tab, combobox, dialog, …) in `bubblegum/core/elements/query.py`.
- Parser additions in `bubblegum/core/parser/instruction.py` covering
  `Select X from Y` (no "dropdown" suffix needed), `Click X link`,
  `<verb> X radio`, `Check/Uncheck/Tick/Untick X`, `Toggle X`,
  `Upload/Attach X to/as Y`, and the `"Click that … visible"` verify
  carve-out.
- Adapter dispatch table in `bubblegum/adapters/web/playwright/adapter.py`
  with new `select` / `upload` / `check` / `uncheck` execution paths.
- `BubblegumSession` scope stack + `close_dialog()` helper in
  `bubblegum/session.py` and `bubblegum/core/scope.py`.
- DOM helpers `find_open_dialog` and `follow_aria_controls` in
  `bubblegum/core/grounding/dom_helpers.py`.
- Widget lab under `examples/web/widgets/widget_lab/` — 6 static pages
  + 7 Playwright scenarios (`run_example.py`). Now supports `--strict`.
- Tier 1 regression runner at `scripts/run_widget_lab_regression.py`
  with `--strict` and `--public` flags. Writes JSON to
  `artifacts/widget_lab_regression.json`.

### 22E-1 — NL-only resolution proved end-to-end
- Kind-hint bias in `accessibility_tree.py` + `fuzzy_text.py`:
  aligned candidates get `confidence + 0.03` AND `role_match = 1.0`;
  non-aligned candidates get `role_match *= 0.7`.
- Snapshot regex (both resolvers) accepts `role "name"`,
  `role: value`, AND `role "name": value` forms.
- `infer_action_type` now uses **leading-verb priority** over substring
  match — `"Click Select country"` is `action=click`, not `action=select`.
- `role_fit_score(click, role)` upgrades: `combobox → 1.0`,
  `option → 0.8`.
- Synthetic probe at `tests/unit/test_phase22e1_nl_only_lab_probe.py`
  (24 cases) runs the full Tier-1+Tier-2 pipeline through the
  CandidateRanker so probe results reflect production ordering.

### Validation evidence
- `python scripts/run_widget_lab_regression.py` → 7/7 (safety-net mode).
- `python scripts/run_widget_lab_regression.py --strict` → 7/7 (NL-only).
- `python scripts/run_widget_lab_regression.py --public` → 11/11.
- Full unit suite: **1,106 passing**, 17 baseline failures unrelated
  to this branch (`pytest-asyncio` + `AsyncMock` issues on `test_phase2`,
  `test_phase15b/f`, `test_phase1b`, `test_anthropic_provider`,
  `test_session`).

---

## What's queued

Picked in this order based on the original "simple to use, powerful
library for tests" goal:

| PR | Scope | Estimated size |
|---|---|---|
| **22E-2** | `@pytest.fixture bubblegum_web`, `widget_lab`, `@pytest.mark.bubblegum` marker. Removes session/page setup boilerplate from every test. | S |
| **22E-3** | Widget state probes on `BubblegumSession` (`is_checked`, `selected_value`, `is_visible`) + auto-screenshot on failure to `artifacts/<test>-<step>.png`. | S–M |
| **22E-4** | Self-hosted minimal MUI sample under `examples/web/widgets/mui_lab/` with 4 scenarios (select / checkbox / dialog / autocomplete). Validates the original "React + MUI" ask. | M |
| **22E-5** | Tier 2 widgets — `tabs`, `accordion`, `slider`. Parser + dispatch + lab pages + regression rows. | M |

### Small follow-ups (drop into any PR or batch)
- **`_do_click` 5-second `wait_for_url` cosmetic** in
  `bubblegum/adapters/web/playwright/adapter.py`. Currently every click
  waits up to 5 s for SPA navigation even on radios / checkboxes /
  options that never navigate. Skipping the wait for known
  non-navigating roles (or shortening the window) drops `radio-group`
  and `link-vs-button` durations from 5 s each.
- **Nameless-combobox resolver fallback.** The lab fix in 22E-1f added
  `aria-label` to make the combobox accessible; real-world pages that
  forget will still leave Bubblegum unable to resolve a `combobox:` row
  with no quoted name. Fallback strategy: `role=combobox` +
  `text=<inline-value>` or use the trigger's text as the locator name
  for sites that violate the ARIA name rules.

### Deferred (explicitly out of Tier 1 + 2)
- BDD step library (behave / pytest-bdd). Easy to add later.
- Flutter Web canvas adapter (separate adapter project).
- React Native native widgets via Appium (mirrors 22D-3 dispatch).
- MUI/Angular Material full demo suites (after Tier 1+2 stabilizes).
- AI/OCR fallback, drag-drop, rich text editors, iframe scoping —
  per the Phase 22D design doc.

---

## Key file map

```
bubblegum/
  adapters/web/playwright/adapter.py            22D-3 dispatch table
  core/
    elements/query.py                           ControlKind enum
    grounding/
      dom_helpers.py                            find_open_dialog, follow_aria_controls
      ranker.py                                 CandidateRanker (signal weights)
      signals.py                                role_fit_score
      resolvers/
        accessibility_tree.py                   Tier 1, kind bias, snapshot regex
        fuzzy_text.py                           Tier 2, mirrors bias
    parser/instruction.py                       infer_action_type, decompose,
                                                parse_relational_intent
    scope.py                                    SessionScope, close_dialog_web
  session.py                                    BubblegumSession + scope methods

examples/web/widgets/widget_lab/
  pages/*.html                                  6 lab pages + link target
  run_example.py                                7 scenarios, --strict

scripts/run_widget_lab_regression.py            --strict, --public, --json

tests/
  benchmarks/web_widgets/parser_cases.json      golden parser dataset
  unit/
    test_phase22d{1,2,3,6,7}_*.py               22D framework tests
    test_phase22e1_nl_only_lab_probe.py         22E-1 probe (24 cases)
```

---

## How to validate locally

```bash
pip install -e ".[web]"
python -m playwright install chromium

# Lab + 22E-1 probe + 22D framework
python -m pytest tests/unit -q

# Lab regression (default safety-net mode)
python scripts/run_widget_lab_regression.py

# The milestone — NL-only strict mode
python scripts/run_widget_lab_regression.py --strict

# Optional: public site smoke
python scripts/run_widget_lab_regression.py --public
```

Expected: 1,106 unit tests passing (17 baseline async-mock failures
unrelated). Lab regression 7/7 in both default and strict modes.
With `--public`: 11/11.

---

## Resuming in a fresh session

Open the new chat with: **"Continue Phase 22 from `docs/phase-22-handoff.md`. Start 22E-2."**

That single line plus this doc is the full context the next session needs.
