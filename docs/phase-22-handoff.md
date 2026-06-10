# Phase 22 — Handoff

Status: Phase 22D + 22E-1 + **22E-2 through 22E-9 shipped end-to-end —
the Phase 22E queue is complete**.
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

### 22E-6 — Nav-wait skip on non-navigating roles (shipped)
- `_do_click` skips the cosmetic 5 s `wait_for_url` probe when the
  resolved target's ARIA role is in `_NON_NAVIGATING_ROLES` (radio,
  checkbox, switch, option, tab, combobox, menuitemcheckbox,
  menuitemradio, slider, spinbutton). Role comes from `target.metadata["role"]` with
  a `role=<role>[name=...]` ref-parse fallback (`_target_role`).
- Action dispatch table + `_execute_action` now thread the
  `ResolvedTarget` through to handlers; only `_do_click` consumes it.
- Skips are observable: `target.metadata["nav_wait_skipped"]` /
  `"nav_wait_skipped_role"` set on the skip path. Buttons, links, CSS
  and text refs (unknown role) keep the probe — navigation still
  detected.
- Saves the full 5 s per click on `radio-group` / `tabs-click` /
  `combobox-select` / `mui-select` style steps; every toggle or
  popup-trigger click in a suite gets the win. Validated on real
  Chromium: radio-group 106 ms, tabs-click 66 ms (was ~5 s each).

### 22E-7 — goto() + shared-browser fixture split (shipped)
- `BubblegumSession.goto(url, wait_until="domcontentloaded")` — web-only
  navigation so tests don't reach into `session.page`.
- `bubblegum_browser` (session-scoped, `loop_scope="session"`): one
  Chromium launch per pytest session.
- `bubblegum_page` (function-scoped, `loop_scope="session"`): fresh
  incognito context + page per test on the shared browser; same
  contract as `bubblegum_web` (label, artifacts dir, failure
  screenshot on teardown).
- Consumers of `bubblegum_page` must run on the session event loop —
  Playwright objects are loop-bound:
  `pytestmark = pytest.mark.asyncio(loop_scope="session")`.
- `bubblegum_web` unchanged (still launches per test) for full
  backward compatibility.
- Follow-up folded in: `asyncio_default_fixture_loop_scope =
  "function"` set in pyproject — the pytest-asyncio deprecation
  warning on every run is gone.

### 22E-8 — bubblegum_mobile Appium fixture (shipped)
- `bubblegum_mobile` (async, function-scoped): builds an Appium driver
  and wraps it in `BubblegumSession.mobile`. Mirrors `bubblegum_web` —
  label, artifacts dir, failure screenshot on teardown.
- CLI options `--bubblegum-appium-url` (default
  `http://localhost:4723`) and `--bubblegum-capabilities` (path to a
  JSON file OR inline JSON object; must include `platformName`).
- Driver-construction logic lives in `bubblegum/testing/appium_driver.py`
  (`load_capabilities`, `build_appium_options`, `create_appium_driver`)
  so it's unit-testable without a device. `build_appium_options` picks
  `UiAutomator2Options` (android) / `XCUITestOptions` (ios) across
  Appium Python Client v3.x–v5.x import layouts.
- `BubblegumSession.capture_failure_screenshot` extended for mobile:
  uses the Appium driver's `get_screenshot_as_png()` (was web-only).
- Skips cleanly when appium-python-client is missing, no capabilities
  are passed, or the Appium server is unreachable.

### 22E-9 — Acme Notes sample app + tester quickstart (shipped)
- `examples/web/real_local/` — three-page login → dashboard → settings
  app (plain HTML + a few lines of JS, no backend). Demo credentials
  `tester` / `bubblegum!`. `run_example.py` drives the whole flow
  NL-only and prints a step summary; `--headed` to watch.
- `sample_app` fixture (session-scoped) in the plugin serves the pages
  via the shared static-server helper. `find_pages_dir` grew a `rel`
  parameter so any example app can be located the same way.
- Dogfooding fix shipped: `is_visible("Welcome back, tester.")` style
  probes resolved to `role=paragraph[name=...]` / `role=status[name=...]`
  refs that match zero elements (those roles don't take their accessible
  name from content), and Playwright reports `is_visible() == False` for
  zero matches. `_resolve_probe_locator` now falls back to an exact
  `get_by_text` match when the role locator matches nothing.
- `docs/getting-started-for-testers.md` rewritten around the real API:
  install → run the sample → first pytest test → session API table →
  `bubblegum_page` fast path → mobile → CLI reference →
  troubleshooting. The integration test runs the exact documented
  flows so the docs stay continuously proven.

### Validation evidence (head of branch)
- `python -m pytest tests/unit -q` → **1,211 passed** with the mobile
  extra installed (3 of those skip without appium-python-client), 17
  baseline failures unrelated to this branch (the documented anthropic
  + `AsyncMock`/`_FakePage` issues).
- `python scripts/run_widget_lab_regression.py --strict` → **10/10**.
- `python scripts/run_mui_lab_regression.py --strict` → **4/4**.
- `python -m pytest --playwright -m bubblegum -v` → **21 passed**,
  1 skipped (2 + 3 + 4 + 3 + 3 + 3 + 3 across 22E-2 / 3 / 4 / 5 / 6 /
  7 / 9; the skip is the `--appium`-gated 22E-8 test).
- 22E-8 validated **live on a real Android emulator** (2026-06-10,
  macOS): Appium 2.19 + UiAutomator2 + ApiDemos — `--appium` run →
  **1 passed in 8.03s** through the `bubblegum_mobile` fixture.
- 22E-6/7 runtime wins confirmed on real Chromium: radio-group 86 ms,
  tabs-click 66 ms, combobox-select 111 ms, mui-select 169 ms (each
  was ~5 s before the nav-wait skip).
- Browser rows validated locally (macOS, real Chromium, 2026-06-10):
  10/10 widget lab, 4/4 MUI lab, 15/15 `-m bubblegum`. 22E-6 runtime
  win confirmed: radio-group 106 ms, tabs-click 66 ms, slider-set
  63 ms (each was ~5 s before the nav-wait skip).

---

## What's queued (next session — pick one)

**The Phase 22E queue is empty — 22E-2 through 22E-9 all shipped.**
Next session picks from the follow-ups below, the deferred list, or a
new phase plan (e.g. PyPI packaging, CI pipeline, BDD step library).

### Small follow-ups (drop into any PR or batch)
- **Nameless-combobox resolver fallback** for ARIA-name-less comboboxes
  in the wild (use trigger inline text or `text=<inline-value>`).

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
  pytest_plugin.py                            22E-2/3 fixtures, hookwrapper,
                                              22E-7 browser/page split,
                                              22E-8 bubblegum_mobile
  session.py                                  22E-3 probes + auto-screenshot,
                                              22E-7 goto(),
                                              22E-8 mobile failure screenshot
  testing/widget_lab.py                       shared static-server helper
                                              (+rel param, 22E-9)
  testing/appium_driver.py                    22E-8 caps + driver builder
  adapters/web/playwright/adapter.py          dispatch table (set added),
                                              22E-6 nav-wait skip
  core/
    elements/query.py                         ControlKind (SLIDER added)
    parser/instruction.py                     parser + relational intent
    grounding/
      signals.py                              role_fit_score (set added)
      resolvers/
        accessibility_tree.py                 Tier 1, slider in kind map
        fuzzy_text.py                         Tier 2, slider in kind map

examples/web/
  widgets/widget_lab/                         10 scenarios + 10 pages
  widgets/mui_lab/                            4 scenarios + 4 MUI pages
  real_local/                                 22E-9 Acme Notes sample app
                                              (3 pages + run_example.py)

docs/
  getting-started-for-testers.md              22E-9 quickstart rewrite

scripts/
  run_widget_lab_regression.py                10 rows (+strict, +public)
  run_mui_lab_regression.py                   4 rows (+strict)

tests/
  unit/test_phase22e{2..9}_*.py               fixture / probe / smoke / parser / nav-wait / goto / mobile / sample-app
  integration/test_phase22e{2..7,9}_*.py      --playwright-gated live tests
  integration/test_phase22e8_*.py             --appium-gated live test
```

---

## How to validate locally

```bash
pip install -e ".[web,test]"
python -m playwright install chromium

# The "first 60 seconds" sample app (22E-9)
python examples/web/real_local/run_example.py               # 7/7 steps

# Full unit baseline — expect 1,211 passed, 17 baseline failures
# (3 of the passes skip without `pip install -e ".[mobile]"`)
python -m pytest tests/unit -q

# Widget lab regression (strict NL-only)
python scripts/run_widget_lab_regression.py --strict        # 10/10
python scripts/run_widget_lab_regression.py --public        # 14/14

# MUI lab regression (strict NL-only)
python scripts/run_mui_lab_regression.py --strict           # 4/4

# All bubblegum-marked integration tests
python -m pytest --playwright -m bubblegum -v               # 21 passed, 1 skipped

# Mobile fixture (requires Appium server + device; 22E-8)
pip install -e ".[mobile]"
python -m pytest --appium -m bubblegum \
  --bubblegum-capabilities '{"platformName":"Android",\
"appium:deviceName":"emulator-5554",\
"appium:appPackage":"io.appium.android.apis",\
"appium:appActivity":".ApiDemos",\
"appium:automationName":"UiAutomator2"}' \
  tests/integration/test_phase22e8_mobile_fixture.py        # 1 passed
```

---

## Resuming in a fresh session

The Phase 22E queue is complete. Open the next chat with:
**"Continue from `docs/phase-22-handoff.md`. Phase 22E is done — plan
the next phase."** (or name a follow-up / deferred item from the lists
above). This doc is the full context the next session needs.
