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
| 5 — Scale & governance | X1, X2, M5, X3, M6 | ✅ done |

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

### Sprint 4 complete. Sprint 5 (scale & governance): X1 → X2 → M5 → X3 → M6.

### What shipped (Sprint 5, in progress)

- **X1** — flaky-test detection / quarantine. Tracks per-step pass-rate **across runs** in a new
  `bubblegum_flaky` table in the SQLite memory layer (`record_flaky_outcome`/`flaky_rows`; counts
  accumulate, unlike the cache's reset-on-success counters). Pure logic in `core/flaky.py`:
  `step_identity` (stable key from NL action + screen signature), `classify` (flaky ⇔ ≥min_runs, has
  both a pass and a fail, pass-rate < threshold — distinct from "always fails"=broken), `summarize`
  (flaky-first ranking), and `FlakyTracker` (records one outcome per step per run, dedupes within a
  run with fail-wins). `FlakyConfig` (`enabled`, `stability_threshold` 0.90, `min_runs` 3,
  `quarantine`). Flaky JSON report (`reporting/flaky_report.py`, `--bubblegum-flaky-report`). JUnit
  integration: flaky steps get `flaky`/`pass_rate`/`runs` properties + a `<system-out>` note; with
  `--bubblegum-quarantine`, a flaky *failure* is downgraded to `<skipped>` (mark-but-not-fail) so it
  doesn't fail the CI build. Plugin records the run at `pytest_sessionfinish` (best-effort, never
  breaks a run). Unit-tested end-to-end (classification, DB accumulation, tracker, report, JUnit
  badges + quarantine); X1 is CI infra with no browser-gated test.
- **X2** — cost budget hard-stop + LLM decision caching. (a) `core/cost.py`: a process-global
  `CostTracker` turns provider token counts (`CompletionResult.input/output_tokens`) into estimated
  USD via a per-model price table; new `grounding.max_run_cost_usd` (0 = disabled) sets a per-run
  ceiling. The LLM resolver records spend after each call; `GroundingEngine` checks
  `cost.budget_exceeded()` *before* Tier 3 and raises `AICostPolicyBlockedError` once the budget is
  reached (hard-stop), mirroring the `max_cost_level=low` block. (b) `core/llm_cache.py`: a
  process-global LLM decision cache keyed on screen signature + instruction + action_type, so a
  repeated AI-resolved screen replays its targets with zero model calls (distinct from the disk
  element memory cache; reset per run). Budget wired in `sdk.configure_runtime`. Unit-tested
  (estimation, tracker budget/reset, cache key/get/put/copies, resolver cache-replay + cost
  accounting, engine Tier-3 hard-stop). No browser-gated test (AI/infra; would need `--llm`).

- **M5** — device cloud integration (BrowserStack / Sauce Labs / LambdaTest / pCloudy). New
  `bubblegum/testing/cloud.py`: an Appium-free, pytest-free provider registry + capability builder.
  `CloudProvider` records each cloud's vendor capability namespace (`bstack:options` / `sauce:options`
  / `LT:Options` / `pCloudy_Options`), default hub URL, and credential key names (vendors disagree:
  `userName` vs `username` vs `user`). `build_cloud_capabilities` turns "a Pixel 8 on BrowserStack
  running my app" into a full W3C caps dict (validates one app-launch strategy — `app` /
  `app_package`+`app_activity` / `bundle_id` — and platform/bundle mismatches → `CloudConfigError`);
  `apply_cloud_options` cloud-ifies an existing caps dict; `cloud_hub_url`/`resolve_credentials`
  resolve the hub + secrets (explicit → `BUBBLEGUM_CLOUD_USERNAME`/`_ACCESS_KEY` → the provider's own
  env vars like `SAUCE_USERNAME`). Driver helper `create_cloud_appium_driver` in
  `testing/appium_driver.py`. Wired into the `bubblegum_mobile` fixture via
  `--bubblegum-cloud-provider` (enriches `--bubblegum-capabilities`, defaults to the provider hub
  unless `--bubblegum-appium-url` is overridden). The real-env cloud smoke harness now sources its
  namespaces/URLs from this registry (single source of truth, no drift). Unit-tested end-to-end
  (registry, hub/credential resolution incl. env precedence, per-provider caps, app-launch validation,
  `apply_cloud_options` immutability/merge); cloud runs are `--appium`/real-env-gated. Docs in
  `docs/mobile-cloud.md`.

- **X3** — coordinate-based vision clicking. When a vision/OCR target can't be deterministically
  hydrated to a DOM/hierarchy element (canvas, image-only, custom-drawn UI), click the bounding-box
  **center** coordinate instead. Pure geometry/ref encoding in `core/coordinates.py` (`bbox_center`,
  `coordinate_ref`/`parse_coordinate_ref`/`is_coordinate_ref` for the `point://x,y` scheme;
  fail-closed on malformed/negative/zero-area input — never clicks `(0,0)`). The `VisualRefHydrator`
  gains a `_coordinate_fallback`: deterministic element mapping still wins first; only when it fails
  *and* the new `grounding.coordinate_click_fallback` opt-in is on *and* the action is click/tap *and*
  a usable bbox exists does it emit a `point://` ref (`hydration_strategy="coordinate"`). Both adapters
  recognize `point://` and click the raw coordinate: Playwright `page.mouse.click(x,y)`, Appium
  `driver.tap([(x,y)])` — click/tap only (typing needs a real element). Flag threaded via
  `intent.context` in `_merge_context`; default OFF (a blind click is riskier than an element click).
  Unit-tested (geometry, ref round-trip/validation, hydrator fallback gating + deterministic
  precedence, web/mobile coordinate execution via fakes); real-browser canvas test in
  `tests/integration/test_coordinate_click_web.py` (`--playwright`-gated). Docs in
  `docs/coordinate-clicking.md`. Targets carry an explicit structured `ResolvedTarget.point` (`[x,y]`)
  that the adapters dispatch on; the `point://x,y` ref is kept only as a readable label.

- **M6** — network-condition simulation (mobile). Device-level NL verbs for connection state, routed
  before grounding exactly like the M2 system verbs (reusing `SystemAction` + `_act_system` so there's
  no new result/error plumbing). New `core/mobile/network_conditions.parse_network_condition`
  (start-anchored, so "Click the Wi-Fi settings row" isn't hijacked) → two kinds: `set_connectivity`
  (offline / online / airplane / wifi / mobile-data toggles) and `set_network_speed` (2G/3G/4G/5G/edge/
  lte/full profiles → Android emulator `netspeed` tokens). `sdk.act` now tries `parse_system_action`
  then `parse_network_condition`. Dispatch in `AppiumAdapter.execute_system_action` →
  `_apply_connectivity` (Android `mobile: setConnectivity`; offline cuts all radios, online restores
  wifi+data) and `_apply_network_speed` (`mobile: networkSpeed`). Honest limits: connectivity works on
  real devices + emulators, speed throttling is Android-emulator-only, iOS radio toggles raise rather
  than silently no-op. Unit-tested (parser table incl. negative/non-hijack cases, per-state/per-platform
  dispatch via a fake driver, sdk routing-before-grounding); `--appium`-gated device flow in
  `tests/integration/test_mobile_network_conditions_appium.py`. Docs in `docs/mobile-network-conditions.md`.

### Sprint 5 complete. Backlog (X1, X2, M5, X3, M6) shipped.

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
