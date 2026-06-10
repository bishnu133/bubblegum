# Phase 22 — Handoff

Status: Phase 22D + 22E-1 + **22E-2 through 22E-5 shipped end-to-end**.
The widget lab runs 10/10 scenarios NL-only against real Chromium with
no `selector=`, `action_type=`, or `input_value=` safety nets. The MUI
lab adds 4 React-shaped scenarios (select / checkbox / dialog /
autocomplete). The pytest plugin exposes `bubblegum_web` + `widget_lab`
fixtures with auto-screenshot on failure.

Use this doc as the entry point when resuming work in a fresh session.
The conversation history is not needed — every relevant file path,
acceptance gate, and queued PR is captured below.

---

## What shipped on `claude/eager-brown-p3k9ee`

### 22D — Tier 1 widget expansion (shipped)
- Closed vocabulary `ControlKind` (link, radio, checkbox, switch, tab, combobox, dialog, slider) in `bubblegum/core/elements/query.py`.
- Parser additions in `bubblegum/core/parser/instruction.py`.
- Adapter dispatch table in `bubblegum/adapters/web/playwright/adapter.py`.
- `BubblegumSession` scope stack + `close_dialog()` helper.
- Widget lab under `examples/web/widgets/widget_lab/`.

### 22E-1 — NL-only resolution proved end-to-end (shipped)

### 22E-2 — Pytest fixtures + `bubblegum` marker (shipped)
- `widget_lab` (session-scoped) fixture: yields base URL of the lab's
  static-server. Shared helper at `bubblegum/testing/widget_lab.py`.
- `bubblegum_web` (async, function-scoped) fixture: launches Chromium,
  wraps the page in a `BubblegumSession`. Honours `--bubblegum-headed`,
  skips when Playwright is missing.
- `@pytest.mark.bubblegum` marker registered (pyproject.toml + plugin).
- `BubblegumSession.page` / `.driver` / `.channel` properties.

### 22E-3 — State probes + auto-screenshot (shipped)
- `is_checked(target)` / `selected_value(target)` / `is_visible(target)`
  on `BubblegumSession` — NL targets routed through `sdk.act(dry_run=True,
  action_type="verify")` then converted to a Playwright locator.
- `BubblegumProbeError` raised when the probe target is unresolved.
- Step-level auto-screenshot in `act / verify / extract / recover`:
  writes `<artifacts>/<label>-step<N>.png` on `status="failed"`.
- Test-level auto-screenshot via `pytest_runtest_makereport` hookwrapper
  + `bubblegum_web` fixture finalizer: writes
  `<artifacts>/<sanitized-nodeid>-final.png` on test-level failure.

### 22E-4 — Self-hosted MUI lab (shipped)
- `examples/web/widgets/mui_lab/` with 4 pages (select, checkbox,
  dialog, autocomplete). Real MUI classnames + ARIA, no Node/bundler.
- `run_example.py` + `scripts/run_mui_lab_regression.py`.
- Local `mui_lab` fixture pattern in
  `tests/integration/test_phase22e4_mui_lab.py` — points the shared
  server helper at any `pages_dir`.
- Dogfooding fix shipped: `pointer-events: none` on `.MuiSvgIcon-root`
  so the checked-state SVG doesn't trap clicks.

### 22E-5 — Tier 2 widgets: tabs, accordion, slider (shipped)
- Parser: `set` / `expand` / `collapse` verbs; trailing widget suffix
  grows by `accordion|section|panel|slider`; `Set X to N` target-first
  regex (distinct from value-first `Enter X into Y`).
- Resolvers: `slider` → `{slider, spinbutton}` kind alignment.
- Signals: `role_fit_score("set", "slider"|"spinbutton") == 1.0`.
- Adapter: new `_do_set` handler (JS evaluate + `input` / `change`
  dispatch). `ActionPlan.action_type` Literal extended with `"set"`.
- Lab pages: `tabs.html` / `accordion.html` / `slider.html` + 3
  scenarios appended to `widget_lab/run_example.py`.
- Dogfooding fixes shipped: accordion chevron in `aria-hidden` span
  (was `::after` pseudo-element folded into a11y name); slider runner
  reads `<output>` via `inner_text` (was crashing on `input_value`).

### Validation evidence (head of branch)
- `python -m pytest tests/unit -q` → **1,159 passed**, 17 baseline
  failures unrelated to this branch (the documented anthropic +
  `AsyncMock`/`_FakePage` issues).
- `python scripts/run_widget_lab_regression.py --strict` → **10/10**.
- `python scripts/run_mui_lab_regression.py --strict` → **4/4**.
- `python -m pytest --playwright -m bubblegum -v` → **12 passed**
  (2 + 3 + 4 + 3 across 22E-2 / 3 / 4 / 5).

---

## What's queued (next session — pick one)

Picked in order of return on the original "simple to use, powerful
library for tests" goal:

| PR | Scope | Estimated size | Why |
|---|---|---|---|
| **22E-6** | `_do_click` cosmetic `wait_for_url` skip for known non-navigating roles (radio / checkbox / option). Drops ~5 s per scenario from `radio-group`, `link-vs-button`, `tabs-click`, `accordion-expand`. | S | Visible runtime win for every tester; pure adapter change. |
| **22E-7** | `BubblegumSession.goto(url)` + session-scoped `bubblegum_browser` / function-scoped `bubblegum_page` fixture split (vs today's everything-per-test). Suites with 50+ tests drop dramatically in wall-clock. | S–M | Most user-visible suite ergonomics improvement. |
| **22E-8** | `bubblegum_mobile` async fixture: Appium driver + `BubblegumSession.mobile`. CLI options `--bubblegum-appium-url`, `--bubblegum-capabilities`. Mirrors `bubblegum_web` API. | M | First-class mobile parity. Unblocks the mobile side of the "real local script" plan I sketched earlier. |
| **22E-9** | `examples/web/real_local/` — minimal multi-page sample app (login → dashboard → settings) served by the shared helper, demonstrated through `bubblegum_web` + a `sample_app` fixture. Plus `docs/getting-started-for-testers.md` rewrite. | M | The "first 60 seconds" surface a new user judges the library by. |

### Small follow-ups (drop into any PR or batch)
- **Nameless-combobox resolver fallback** for ARIA-name-less comboboxes
  in the wild (use trigger inline text or `text=<inline-value>`).
- `asyncio_default_fixture_loop_scope` set to silence the pytest-asyncio
  deprecation warning shown on every run.

### Deferred (explicitly out of Tier 1 + 2)
- BDD step library (behave / pytest-bdd).
- Flutter Web canvas adapter.
- React Native native widgets via Appium (mirrors 22D-3 dispatch).
- MUI / Angular Material full demo suites (after Tier 1 + 2 stabilizes).
- AI / OCR fallback, drag-drop, rich text editors, iframe scoping.

---

## Key file map

```
bubblegum/
  pytest_plugin.py                            22E-2/3 fixtures, hookwrapper
  session.py                                  22E-3 probes + auto-screenshot
  testing/widget_lab.py                       shared static-server helper
  adapters/web/playwright/adapter.py          dispatch table (set added)
  core/
    elements/query.py                         ControlKind (SLIDER added)
    parser/instruction.py                     parser + relational intent
    grounding/
      signals.py                              role_fit_score (set added)
      resolvers/
        accessibility_tree.py                 Tier 1, slider in kind map
        fuzzy_text.py                         Tier 2, slider in kind map

examples/web/widgets/
  widget_lab/                                 10 scenarios + 10 pages
  mui_lab/                                    4 scenarios + 4 MUI pages

scripts/
  run_widget_lab_regression.py                10 rows (+strict, +public)
  run_mui_lab_regression.py                   4 rows (+strict)

tests/
  unit/test_phase22e{2,3,4,5}_*.py            fixture / probe / smoke / parser
  integration/test_phase22e{2,3,4,5}_*.py     --playwright-gated live tests
```

---

## How to validate locally

```bash
pip install -e ".[web,test]"
python -m playwright install chromium

# Full unit baseline — expect 1,159 passed, 17 baseline failures
python -m pytest tests/unit -q

# Widget lab regression (strict NL-only)
python scripts/run_widget_lab_regression.py --strict        # 10/10
python scripts/run_widget_lab_regression.py --public        # 14/14

# MUI lab regression (strict NL-only)
python scripts/run_mui_lab_regression.py --strict           # 4/4

# All bubblegum-marked integration tests
python -m pytest --playwright -m bubblegum -v               # 12 passed
```

---

## Resuming in a fresh session

Open the new chat with: **"Continue Phase 22 from
`docs/phase-22-handoff.md`. Start 22E-6."**

(Or pick any other queued PR from the table above.) That single line
plus this doc is the full context the next session needs.
