# Bubblegum — Post-MVP Enhancement Backlog: progress & handoff

Tracks the implementation of the *Post-MVP Enhancement Backlog* against this
repo. Sprints 1 & 2 are complete and verified (unit + real-browser). This doc is
the handoff for continuing with Sprint 3+.

## Status

| Sprint | Items | Status |
| --- | --- | --- |
| 1 — Reporting / quick wins | C0, R1, W3, R2, A3, V2 | ✅ done |
| 2 — Flakiness + speed | W2, W1, R3, P1, W4 | ✅ done |
| 3 — Authoring + verify depth | A1, A2, V1 | ✅ done |
| 4 — Mobile depth | M1, M2, M4 | ✅ done |
| 5 — Scale & governance | X1, X2, M5, X3, M6 | ⏳ |

### What shipped (Sprint 1 & 2)

- **C0** — behavioral test proving config thresholds change tier behavior (wiring already existed).
- **R1** — JUnit XML report (`--bubblegum-report-junit`), `reporting/junit_report.py`.
- **W3** — soft assertions: `s.soft_assertions()` / `verify(soft=True)`, `metadata["soft"]`.
- **R2** — Allure results (`--bubblegum-report-allure`), `reporting/allure_report.py` (stdlib-only).
- **A3** — `s.explain(step)` + `reporting/explain.py` (renders existing trace/signal data).
- **V2** — a11y assertions `verify(assertion_type="a11y")`, vendored axe-core 4.11.0 under
  `bubblegum/testing/vendor/axe-core/` (MPL-2.0 NOTICE), `[a11y]` extra, `core/a11y.py`.
- **W2** — `wait_until_stable` quiescence before every step (web MutationObserver+networkidle+spinner;
  mobile hierarchy poll), `GroundingConfig.stability_*`, default ON, per-call override.
- **W1** — API auth bootstrap: `BubblegumSession.web(page, bootstrap=...)` / `.mobile(driver, bootstrap=...)`,
  runs once on `__aenter__`. Example in `examples/web/auth_bootstrap/`.
- **R3** — self-healing suggested fix (`old_ref`/`new_ref`/`suggested_fix`) + brittleness ranking
  (`analytics.healing_summary.brittleness`) + `--bubblegum-suggest-fixes`, `reporting/suggested_fixes.py`.
- **P1** — parallel-safe memory cache: SQLite **WAL + busy_timeout** in `core/memory/layer.py`
  (proven under real `pytest -n 4`). Docs in `docs/ci.md`.
- **W4** — network assertions `verify(assertion_type="network", expected_value="POST /api/login 200")`,
  `core/network.py` matcher + per-page response recorder in the Playwright adapter.

### What shipped (Sprint 3, in progress)

- **A1** — recorder / codegen + first CLI. New `bubblegum record --url ... --out flow.py`
  (`bubblegum/cli/`, `[project.scripts] bubblegum = "bubblegum.cli:main"`). Captures a manual
  click-through via an injected JS recorder (`add_init_script` + `expose_binding`, **not** a
  codegen subprocess) and emits runnable NL steps (`act("Click Login")`, `act('Enter "tom" into
  Username')`) with the resolved selector as a `# fallback:` comment. Browser-free core in
  `bubblegum/core/recorder/`: `RECORDER_JS` (capture script, a self-executing IIFE — `add_init_script`
  runs the text as-is; text fields captured on `input`, not blur-dependent `change`), `ActionRecorder`
  (binding side + `attach`), `normalize_event`/`coalesce_actions` (capture→action), `derive_steps`
  (action→NL, round-trips through the parser), `emit_script` (runnable `*_recorded.py`). Real-browser
  replay test in `tests/integration/test_recorder_web.py`.
- **A2** — interactive REPL / live-try mode. New `bubblegum repl --url ...` (web) /
  `--appium-url ... --caps ...` (mobile) opens a session and evaluates typed NL steps immediately,
  printing the resolved target + resolver + confidence. Browser-free core in `bubblegum/core/repl/`:
  `parse_repl_line`/`ReplCommand` (grammar: bare NL → act, `act/verify/extract/explain/dry(...)` verb
  calls, `:help`/`:quit`/`:dry`/`:open`/`:explain` meta), `evaluate` (channel-agnostic; reuses
  `dry_run` for resolve-only previews and `s.explain` from A3), `format_result`. CLI loop +
  browser/driver lifecycle in `bubblegum/cli/repl.py` (`repl_loop` takes an injectable line reader so
  it is unit-tested without stdin). Real-browser test in `tests/integration/test_repl_web.py`. Mobile
  path reuses `testing/appium_driver.py`; unverified without a device (consistent with other Appium code).
- **V1** — visual regression assertions. `verify(assertion_type="visual")` captures a screenshot and
  diffs it against a stored baseline. Page-scoped (branches in `sdk.verify` before grounding, like
  a11y/network) → `sdk._verify_visual`. Pure pixel math in `core/visual.py` (`baseline_name`,
  `compare_rgba`, `evaluate_diff`, `highlight_diff_rgba` — stdlib, unit-tested with no deps); PNG
  decode/encode isolated in `core/visual_image.py` behind Pillow (`bubblegum-ai[visual]` extra). New
  `VisualConfig` (`baseline_dir` default `.bubblegum/baselines`, `tolerance`, `channel_threshold`,
  `full_page`, `update_baselines`) + `--bubblegum-update-baselines` flag. First run (or update) writes
  the baseline & passes; a regression writes a highlighted `<name>.diff.png` + `<name>.actual.png` and
  fails. Baselines keyed by a name derived from the instruction ("header matches baseline" → `header`).
  Adapter gains `screenshot_bytes(full_page=...)`. Real-browser test in
  `tests/integration/test_visual_web.py`.

### What shipped (Sprint 4, in progress)

- **M1** — mobile gesture vocabulary. Adds `long_press`, `double_tap`, `pinch`, `zoom`, `drag` to the
  mobile action set. Parsed from NL by `parser.match_gesture` ("Long press the message", "Double tap
  the image", "Pinch/Zoom the map", "Drag the slider right") — gesture verbs are anchored at the start
  so a button named "Long press" is still clicked, and bare "press"/"double click" stay web-safe.
  `ActionPlan.action_type` literal extended. Dispatch in `AppiumAdapter._execute_action` →
  per-platform `mobile:` gestures: Android `longClickGesture`/`doubleClickGesture`/`pinchOpen|Close
  Gesture`/`dragGesture`, iOS `touchAndHold`/`doubleTap`/`pinch`(scale)/`dragFromToForDuration`.
  Long-press duration overridable via numeric `input_value`; drag direction (up/down/left/right) parsed
  into `input_value`. Unit-tested (parser + per-platform dispatch via a fake driver, no device);
  `--appium`-gated device test in `tests/integration/test_mobile_gestures_appium.py` (env-var driven,
  skips without a device — mobile items verify primarily via the unit dispatch tests).

- **M2** — mobile system / hardware actions. NL verbs `press back` / `go back`, `rotate to
  landscape|portrait`, `hide keyboard`, `open deep link <url>` / `open url <url>`, `background app
  [for N seconds]`, `accept biometric`, `open notification [<text>]`. Parsed by
  `core/mobile/system_actions.parse_system_action` (start-anchored so a real "Back" control isn't
  hijacked). Device-level — routed in `sdk.act` *before* grounding (mobile channel, no
  selector/action_type override) to `AppiumAdapter.execute_system_action`: per-platform driver calls
  (Android `press_keycode(4)` / iOS `back()`; `orientation=`; `hide_keyboard()`; `get(url)`;
  `background_app(s)`; `mobile: fingerprint` / `mobile: sendBiometricMatch`; `open_notifications()` +
  best-effort text tap). New `MobileConfig` (`auto_hide_keyboard` — best-effort soft-keyboard hide
  before a mobile tap/click; `background_app_seconds`). Unit-tested (parser + per-platform dispatch +
  sdk routing, no device); `--appium`-gated device test runs the rotate/hide-keyboard/back flow.

- **M4** — UI FrameworkDetector (Compose / Flutter / RN / SwiftUI). New
  `core/mobile/ui_framework_detector.detect_ui_framework` — heuristic, signature-based (class/package
  tokens + platform), distinct from the existing `detect_mobile_surface` (which classifies the
  automation surface, not the UI toolkit). Wired into `AppiumAdapter.collect_context` as
  `app_state["ui_framework"]`; threaded into resolvers via `intent.context["app_state"]`.
  `AppiumHierarchyResolver` applies a **conservative, additive** tweak: Compose/RN tappable controls
  render as generic clickable `View`/`ViewGroup` nodes, so a clickable generic node scores as a real
  control for tap/click (role 0.9 vs default 0.4); native scoring is unchanged. Framework + limits are
  stamped onto each candidate's metadata. Flutter's opacity (semantics/Flutter-driver required) and
  SwiftUI-vs-UIKit ambiguity are reported honestly, not worked around — see `docs/mobile-frameworks.md`.
  Unit-tested (detection across Compose/Flutter/RN/SwiftUI/native hierarchies + resolver gating, no
  device); `--appium`-gated device test confirms the adapter populates `ui_framework`.

### Sprint 4 complete. Next: Sprint 5 (scale & governance): X1 → X2 → M5 → X3 → M6.

**Note on mobile testing:** the sandbox and the usual local gate are browser-only (no Appium device),
so mobile items are verified by unit tests that assert the exact `mobile:` gesture command per platform
via a fake driver. Real-device tests are `--appium`-gated and run only where an emulator/device exists.

## Conventions established (follow these in Sprint 3+)

- **One item at a time:** implement → unit-test → real-browser/integration test → commit → push →
  check in with the user. Each commit message starts with the item id (e.g. `A1: ...`).
- **Tests-to-run block:** end every item with the exact local commands + expected pass counts.
- **Browser/mobile tests are gated:** mark with `pytest.mark.playwright` (and `bubblegum`); they only
  run with `--playwright` (see `tests/conftest.py`). Appium → `--appium`, LLM → `--llm`, memory → `--memory`.
- **Integration test pattern (avoid the event-loop landmine):** use the shared `bubblegum_web` fixture
  (function loop) or `bubblegum_browser` + `pytest.mark.asyncio(loop_scope="session")` — never drive
  `async_playwright().start()/.stop()` manually in a test body. `conftest.py` pushes the sync
  `test_playwright_adapter` module to the end so async tests always run first.
- **Load test pages via `page.goto("data:text/html,"+quote(html))`**, not `set_content` (the latter does
  not fire `add_init_script` hooks).
- **Page-scoped assertions** (a11y, network) branch in `sdk.verify` *before* grounding and return via
  `_page_scoped_result(...)`. Add new ones the same way.
- **Pure logic in `core/`, browser I/O in the adapter, wiring in `sdk.verify`** — keeps most logic
  unit-testable without a browser.
- **No model identifiers** in committed artifacts (commit messages, code, docs).
- Run `python -m pytest tests/unit -q` (fast, no browser) after every change; the full browser suite
  (`python -m pytest tests/integration --playwright`) is the user's local gate.

## Key locations

- SDK entry points: `bubblegum/core/sdk.py` (`act`/`verify`/`extract`/`recover`).
- Session API: `bubblegum/session.py`.
- Web adapter: `bubblegum/adapters/web/playwright/adapter.py`; mobile: `bubblegum/adapters/mobile/appium/adapter.py`.
- Config: `bubblegum/core/config.py`. Reporting: `bubblegum/reporting/`. Pytest plugin/flags: `bubblegum/pytest_plugin.py`.
- Grounding: `bubblegum/core/grounding/` (engine, ranker, resolvers, signals).

## Next: Sprint 3 (authoring + verify depth)

1. **A1 — Recorder / codegen (L, 2+ weeks).** Record a manual click-through and emit Bubblegum NL steps
   (`act("Click Login")`, `act('Enter "tom" into Username')`) with the resolved selector as a fallback
   comment; new CLI `bubblegum record --url ... --out flow.py` (no CLI exists yet — first console entry
   point). Recommend splitting into sub-steps: (a) CLI scaffold/entry point, (b) action capture, (c)
   element→NL-label derivation reusing the a11y tree + ranker, (d) code emission + replay test.
2. **A2 — Interactive REPL / live-try mode.** `bubblegum repl --url ...` evaluating typed NL steps live;
   reuse `dry_run` + `s.explain` (A3). Partial foundation exists (`dry_run`, `print_plan`).
3. **V1 — Visual regression.** `verify(assertion_type="visual")` with baseline capture + pixel/perceptual
   diff under `.bubblegum/baselines/`, `--update-baselines`. Add as a page/element-scoped assertion.
