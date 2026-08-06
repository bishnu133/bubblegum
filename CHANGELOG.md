# Unreleased

## 0.0.8 — fix(web): modal-scoped time/checkbox resolution & exact-label radios

Fixes from real-world testing of an Ant Design portal where three plain-English
steps failed inside a modal/dialog. All three fixes are generic — no
project-specific field or element names in the library — so they hold for any
application on any web tech stack.

- **Exact-label preference for radios & checkboxes.** A phrase can be a whole-word
  *subset* of two option labels — `Select "Required" radio` matched both
  "Required" and "Not Required" equally, so DOM order decided and the wrong one
  ("Not Required") was selected. Both resolvers now add a bounded exactness
  tiebreak: among options whose labels cover the phrase equally, the one whose
  visible label carries the fewest **extra** words wins, so the exact "Required"
  is chosen. The penalty is smaller than the section-context weight, so it only
  breaks otherwise-equal ties and never overrides which option or section matches.
- **Modal-scoped radio & checkbox resolution.** When a blocking modal is open, the
  radio/checkbox the tester means is inside it; a same-labelled control on the
  page behind the mask must not win. Both resolvers now scope to the topmost open
  dialog first (falling back to the whole document only when the dialog has none),
  so every control in a modal is reachable for selection *and* verification.
- **Modal-scoped date-range picker (no time-field hijack).** A "Start time" /
  "End time" field inside a modal was hijacked by a date **range** picker on the
  page behind it — the range resolver scanned the whole document, grabbed the
  background period picker, and typed the time into a date field (slow, wrong
  value). The range resolver is now scoped to the open dialog and yields nothing
  when the dialog has no range picker, so the (also modal-scoped) input finder
  claims the modal's plain/time field instead. Non-modal range pickers are
  unchanged.
- Coverage: `tests/integration/test_modal_radio_checkbox_time_web.py` — exact
  "Required" over "Not Required" (and the superset still reachable when named), a
  modal checkbox over a background copy, the range resolver declining a background
  picker while a modal is open, the modal time field resolving via the input
  finder, and the no-modal range picker still resolving.

## 0.0.7 — feat(mobile): iOS / native system-alert auto-handling

iOS permission dialogs (notifications, location, camera, ATT, Bluetooth, …) — and
Android native alerts — are presented by the OS in a separate process, so they
frequently do **not** appear in the app's page source and can't be tapped by
name-based grounding. They also pop up asynchronously, blocking whatever step
runs next. Bubblegum can now clear them generically via the W3C alert API,
regardless of the app's tech stack.

- **New `AppiumAdapter.handle_system_alert(mode)`** — accepts (affirmative
  button: Allow / OK / While Using the App) or dismisses (negative button) a
  native alert through the standard `/session/{id}/alert/*` endpoints, which
  reach system alerts that hierarchy grounding cannot see. Returns
  `{handled, text, mode}`; never raises (no alert present is a normal outcome).
- **Config `grounding.system_alert_handling`** — `"ignore"` (default), `"accept"`,
  or `"dismiss"`. When set to accept/dismiss, the engine clears any present
  native alert **before every mobile `act`/`verify`/`extract`/`recover`**, so an
  alert that appears mid-flow is handled automatically instead of stalling the
  next step. Mobile-only; a no-op on web and when set to `ignore`.
- Coverage: `tests/unit/test_ios_system_alert.py` — accept/dismiss when present,
  no-alert and action-failure are non-errors, config default, and the SDK gate
  (ignore skips, accept/dismiss call through, web no-op, adapter-without-handler
  safe).

## 0.0.6 — first stable (non-prerelease) release

Graduates `0.0.6a77` to a final release — identical code, a version string with
no pre-release (`a`) suffix. Enterprise package repositories (e.g. Nexus) and pip
skip pre-releases for range specifiers and some proxy policies filter them, so a
stable version resolves cleanly through those toolchains for UAT/production
pipelines (`bubblegum-ai==0.0.6`, no `--pre` needed). No functional change from
a77; supersedes every `0.0.6aNN` alpha (`0.0.6a77 < 0.0.6`). Next development
iteration continues from `0.0.7aN`.

## 0.0.6a77 — fix(mobile): React-Native real-device grounding (whitespace / hang / labelled fields)

Fixes from real-device testing against a React Native app (Healthy 365) where a
plain-English login flow stalled. All three fixes are generic — they hold for any
tech stack, not just RN.

- **Whitespace-tolerant xpath (Bug 3/4).** The hierarchy resolver stripped a text
  node's value for matching but built an exact `@text='…'` locator, which then
  failed on the raw attribute — RN text nodes almost always carry trailing
  whitespace (`"Log in with OTP "`). Generated locators now use
  `normalize-space(@attr)='…'` for text-like attributes (text / content-desc /
  label / name / value), trimming and collapsing whitespace on both sides;
  id-like attributes keep an exact match. Both UiAutomator2 and XCUITest evaluate
  XPath server-side with a full XPath 1.0 engine, so this is supported on both.
- **Type into a labelled field (Bug 1 root).** A field's visible label is
  usually a separate node next to the input (RN, native, Compose, Flutter). New
  `core.mobile.field_association` associates the label named in the step with the
  adjacent input — same-container first, then nearest input below — so
  `Enter "…" into "NRIC or FIN"` targets the right `EditText` (disambiguating
  between multiple inputs by container). It also redirects a `tap` on a
  non-clickable text node to its nearest clickable ancestor. Wired as a mobile
  grounding fallback (`_maybe_resolve_mobile_field`) that runs only on a
  name-based miss.
- **No more session-wedging scroll loop (Bug 1/2).** Scroll-to-find now runs only
  when grounding found *nothing* (`ResolutionFailedError`) — a low-confidence or
  ambiguous miss means the target is already on screen, so scrolling can't help
  and, on an attached/shared Appium session, a pointless scroll+OCR loop tied up
  the session behind the bridge's commands (the observed hang). It also stops as
  soon as a swipe stops changing the screen. This removes the runaway that made a
  failed `type` stall the whole session.
- Coverage: `tests/unit/test_mobile_field_association.py` (label→input incl.
  container disambiguation, self-labelled inputs, clickable-ancestor, guards, SDK
  wrapper), `tests/unit/test_rn_whitespace_xpath.py` (normalize-space for text
  attrs, exact for ids, resolver end-to-end on trailing-space text), and new
  scroll-gating cases in `tests/unit/test_mobile_scroll_to_find.py`
  (skip-on-low-confidence, run-on-resolution-failed, stop-on-unchanged-screen).

## 0.0.6a76 — fix(packaging): installable `localvision` extra (RapidOCR pin)

The a75 `localvision` extra pinned `rapidocr-onnxruntime>=1.3`, a version that
does not exist on PyPI (the `rapidocr-onnxruntime` line tops out at 1.2.x), so
`pip install "bubblegum-ai[localvision]"` failed with "No matching distribution
found". Corrected the pin to `rapidocr-onnxruntime>=1.2.3,<2` in both the
`localvision` and `all` extras. The v1.x `RapidOCR().__call__` → `(result, elapse)`
API the provider consumes is unchanged, so no code change is needed. No engine
behavior change; packaging metadata only.

## 0.0.6a75 — perf(mobile): hierarchy compaction for grounding

A complex app's `page_source` is mostly decorative layout containers — thousands
of nodes with no text, no id, and nothing to interact with. The hierarchy
resolver parsed and built a graph over *every* node on every grounding pass (and
again on each scroll re-ground), so that bulk was pure latency — and on a device
farm, latency near the command timeout is a reliability risk. Bubblegum now
prunes the hierarchy to the nodes that can actually be a target before grounding.

- **New `core.mobile.hierarchy_compaction` (pure, unit-tested).**
  `compact_hierarchy_xml()` keeps every node carrying text / a11y description /
  id / value, plus interactive and scrollable nodes, plus their ancestors — and
  drops decorative textless subtrees and invisible textless nodes. Returns the
  compacted XML + stats (`original_nodes`, `kept_nodes`, `dropped_nodes`,
  `compacted`, `truncated`). On a 500-container screen with one real control it
  reduces to 2 nodes.
- **Parity-safe by construction.** Every candidate-producing node is kept, and
  the resolver's locators are global XPaths (`//tag[@text='…']`) that don't depend
  on the pruned structure — so the *same* candidates resolve, just faster. A
  resolver test asserts byte-identical candidate refs with compaction on vs off,
  including a target buried under 300 decorative nodes.
- **Scoped to grounding only.** Applied inside `AppiumHierarchyResolver`; the full
  `page_source` is left untouched for the readiness / system-dialog / framework
  detectors, which legitimately rely on nodes (progress bars, dialog containers)
  that compaction drops.
- **Config:** `grounding.mobile_hierarchy_compaction` (on by default) and
  `grounding.mobile_hierarchy_max_nodes` (default 1500; advisory — no groundable
  node is ever dropped to meet the cap). Threaded to the resolver via context.
  Mobile-only; no web change.
- Coverage: `tests/unit/test_mobile_hierarchy_compaction.py` — subtree pruning,
  ancestor retention, interactive/invisible handling, empty/unparseable safety,
  large-tree reduction, and resolver candidate parity (on vs off).

## 0.0.6a74 — feat(mobile): readiness & resilience (ANR / crash / session-loss / spinners)

Real apps aren't always ready the instant a screen appears, and long device-farm
runs can lose the Appium session. Bubblegum now reads these conditions and reacts
sensibly instead of failing with a cryptic grounding error: it waits out
spinners, fails fast with an actionable message when the app crashes or stops
responding, and labels a lost session distinctly.

- **New `core.mobile.readiness` (pure, unit-tested).** `detect_mobile_readiness()`
  classifies the current screen from the hierarchy — a live progress/loading
  indicator (Android ProgressBar, iOS ActivityIndicator, Compose/Flutter
  spinners), an ANR ("isn't responding") dialog, or a crash ("has stopped")
  dialog — with hard-blocker precedence (crash > anr > progress).
  `classify_driver_error()` sorts a driver exception into `session_lost` /
  `transient` / `other`. Signatures are deliberately specific (e.g.
  "unfortunately" alone is **not** treated as a crash) to avoid false positives.
- **Progress-aware, ANR/crash-aware stability wait.** `AppiumAdapter.wait_until_stable`
  now keeps waiting (bounded by `stability_timeout_ms`) while a spinner is up even
  once the hierarchy stops changing, and returns early with an `anr`/`crash`
  outcome when a blocking dialog appears — no point waiting on a wedged app. The
  verdict is also recorded in `app_state["readiness"]` on every context snapshot.
- **Fail fast with a clear message.** A new SDK health gate runs after context
  collection in `act()`, `verify()`, and `extract()`: on a crash/ANR it returns a
  failed `StepResult` with an `AppNotReadyError` and an actionable message
  ("relaunch the app / restart the session", "wait for it to recover") instead of
  letting the step fail obscurely at grounding. A spinner is not a hard blocker
  here — the stability wait already handles it.
- **Lost sessions are labeled.** The adapter's retry reason now reports
  `session_lost` for invalid/terminated-session errors (which are never retried in
  place), so reports distinguish a dead session from a transient blip.
- Coverage: `tests/unit/test_mobile_readiness.py` — readiness classification and
  precedence, the "unfortunately is not a crash" guard, driver-error
  classification + retry-reason labeling, the progress-aware / ANR-early-return /
  quiet-stable `wait_until_stable` (fake driver), and the SDK health gate
  (crash/ANR fail, ready/progress/web pass-through).

## 0.0.6a73 — feat(mobile): OCR verify & extract on canvas/Flutter screens

Completes the canvas story for assertions and reads. `verify('the screen shows
"Level 2"')` and `extract('Get the score')` now work on a Flutter/game/canvas
screen, where the accessibility hierarchy has no text to check — the expected
phrase is verified, and text is extracted, from the on-screen OCR/vision
candidates instead. Native screens are unchanged: they still verify/extract from
the hierarchy exactly as before.

- **`verify()` — OCR `text_visible` on routed screens.** After context
  collection, `verify()` runs the same canvas routing as `act()`; on a routed
  screen a new `_maybe_verify_canvas_text()` checks the expected phrase(s) against
  the OCR candidates and returns a finished result — so a canvas screen no longer
  hard-fails at hierarchy grounding. Multiple quoted phrases must all be visible.
  Matching handles a phrase split across OCR boxes (e.g. "Level 2" as "Level" +
  "2") via a whole-screen text fallback.
- **`extract()` — OCR text on routed screens.** `_maybe_extract_canvas_text()`
  returns the on-screen text best matching the target phrase as the extracted
  value, before falling through to element grounding.
- **`ocr_text_present()`** added to `core.mobile.canvas_routing` (pure, unit
  tested): exact/substring per box plus a joined whole-screen match.
- **Honest failures.** On a routed screen with no vision backend configured, the
  verify result carries an actionable message pointing at
  `grounding.vision_backend=rapidocr`.
- Scope: `text_visible` verify and text extract (tap/click stay in a72). No web
  behaviour change; specialized assertions (a11y/network/visual/table/status)
  are dispatched earlier and untouched.
- Coverage: `tests/unit/test_canvas_verify_extract.py` — `ocr_text_present`
  (exact/substring/spanning/absent/empty) and both SDK hooks (pass/fail,
  all-quoted-required, no-candidate actionable error, not-routed/web/non-text
  skips for verify; matched/none/not-routed/no-match for extract).

## 0.0.6a72 — feat(mobile): Flutter/canvas auto-routing to vision

Bubblegum now recognises a self-drawn screen and grounds it by pixels
automatically — the tester never has to know what technology an app was built
with. On a Flutter screen (or a game/engine, a raw GL/Surface view, or any screen
whose accessibility hierarchy exposes no usable text), a plain-English
`act("Tap Play")` resolves by OCR/vision and taps the matched text's coordinate,
while ordinary native screens keep resolving precisely from the hierarchy exactly
as before.

- **New `core.mobile.canvas_routing`.** `evaluate_canvas_routing()` classifies the
  current screen from the hierarchy alone — Flutter (via the UI-framework
  detector), a canvas/engine surface class (FlutterView / GLSurfaceView /
  TextureView / UnityPlayer / …), a hierarchy with nodes but no text, or no
  hierarchy at all — and decides whether to route to vision.
  `select_canvas_vision_candidate()` picks the on-screen OCR/vision candidate
  whose text best matches the step's target. Both are pure and unit-tested.
- **Two SDK hooks, both additive.** `_maybe_route_canvas()` runs after context
  collection: on a routed screen it turns on the coordinate-tap fallback *for that
  step only* (the global default stays off for ordinary screens) and records the
  decision for the report. `_maybe_resolve_canvas_vision()` runs only after
  hierarchy grounding finds nothing — it taps the best OCR match by coordinate,
  bypassing the confidence bands that would otherwise make a vision-only screen
  un-actionable (a perfect OCR match on a canvas screen scores mid-band because it
  has no role/hierarchy support). Tap/click only; typing still needs a real
  element.
- **Degrades honestly.** When a screen routes to vision but no vision backend is
  configured, the decision carries a `vision_backend_not_configured` warning and
  the SDK logs an actionable hint to enable `vision_backend=rapidocr`. Pairs
  directly with the a71 offline OCR backend.
- **Config:** `grounding.canvas_auto_route` (on by default). Mobile-only; a no-op
  on web and on any native screen that exposes text.
- Coverage: `tests/unit/test_canvas_routing.py` — Flutter/canvas/opaque/native/
  absent-hierarchy classification, vision-unavailable warning, candidate selection
  (exact/none/dict inputs), and the SDK hooks (coordinate fallback enabled on
  Flutter but not native, web no-op, config disable, coordinate tap of the best
  match, and the not-routed / typing / no-candidate skips).

## 0.0.6a71 — feat(vision): offline on-device OCR grounding (RapidOCR)

Bubblegum can now ground a step from the **pixels on screen, entirely on the
machine running the test** — no network, no hosted model, no per-call cost. This
is the "works on any technology" path: screens the accessibility hierarchy
cannot describe (Flutter and other canvas-drawn UIs, games, custom-rendered
widgets, DRM-masked views) still resolve a plain-English step, because OCR reads
the visible text and the existing visual-ref hydrator maps a matched box to a tap
coordinate. Screenshots never leave the process, so it is the privacy-clean
default for enterprise apps and the low-latency default on a device farm (only
the screenshot travels back over the wire; OCR runs on the runner).

- **New `rapidocr` vision backend.** A `RapidOCRVisionProvider` implements the
  same `VisionProvider.detect_targets` contract as the hosted backends, returning
  on-screen text candidates (`text`/`label` + axis-aligned `bbox` + score) that
  flow through the already-shipped `VisionModelResolver` → visual-ref hydrator →
  coordinate tap. No resolver, adapter, or hydrator change was needed.
- **Local by construction — one switch to turn on.** `rapidocr` inference runs
  in-process, so it is exempt from the hosted-vision privacy opt-ins: setting
  `grounding.vision_backend: rapidocr` + `grounding.enable_vision: true` is
  enough. `config.vision_enabled` and the SDK privacy/cost gates recognise
  on-device backends (new `LOCAL_VISION_BACKENDS` set), so no `send_screenshots`
  / `vision_is_local` / `process_screenshots_for_vision` flags are required.
- **Optional dependency, fail-safe when absent.** RapidOCR is pulled by the new
  `localvision` extra (`pip install "bubblegum-ai[localvision]"`). When it isn't
  installed the provider stays dormant and returns no candidates, so the
  deterministic + hierarchy tiers are unaffected. Any engine/inference error is
  swallowed to `[]` — a bad frame never fails a step.
- Coverage: `tests/unit/test_rapidocr_vision_backend.py` — polygon→bbox
  conversion, confidence filter, candidate cap, malformed-item skipping, injected
  tuple/bare engines, empty-image and engine-absent fail-safes, factory
  selection, and the config/SDK local-gate behaviour (no privacy opt-in needed
  for `rapidocr`; hosted backends still require it).

## 0.0.6a70 — feat(mobile): selector-less scroll-to-find

A plain-English step that names an off-screen control now resolves without a
selector. When a mobile grounding attempt finds no candidate on the current
screen and the screen has a scrollable container, Bubblegum swipes one page,
re-collects the UI hierarchy, and re-grounds — repeating up to a bounded number
of times — until the named control comes into view. So `act("Tap Accept")` works
even when "Accept" starts below the fold, on native, hybrid, Android, or iOS, and
without naming a locator.

- **Wired the existing bounded scroll-discovery plan into execution.** The
  adapter already computed a `scroll_discovery` plan (scrollable-container
  detection + direction) into `app_state` on every context snapshot, but nothing
  consumed it. `sdk.act()` now calls a new `_maybe_scroll_to_target()` on a
  grounding miss (after the deterministic DOM fallbacks, before the last-resort
  fallback selector). It swipes → re-collects → re-grounds, stops early when the
  fresh plan reports nothing left to scroll, and stamps `scroll_to_find`
  diagnostics (`attempts`, `direction`, `found_after_scroll`) onto the resolved
  target for the report.
- **New `AppiumAdapter.scroll_screen(direction)`** — a screen-relative swipe
  (from the live window size, with a safe fallback) that needs no element, so it
  works even when the target isn't in the hierarchy yet. Directions:
  `down`/`up`/`left`/`right`.
- **Opt-in and bounded, additive by construction.** Gated by
  `grounding.scroll_to_find` (on by default) and
  `grounding.scroll_to_find_max_scrolls` (default 4). Mobile-only and a no-op on
  web and on screens with nothing to scroll; only ever runs on a grounding miss,
  so passing steps and existing behavior are untouched.
- Coverage: `tests/unit/test_mobile_scroll_to_find.py` (fake Appium adapter —
  resolves-after-N-scrolls, never-found cap, web no-op, no-scrollable-plan skip,
  config-disabled skip, early stop at bottom, and `scroll_screen` geometry).
  On-device runs via the env-gated `tests/real_env/android|ios` suites.

## 0.0.6a69 — feat: generic status assertion + modern summary report + console renderer

Three additions, all framework-agnostic and self-contained.

**1. Verify an item's status (tag / badge / chip / pill), any tech stack.** A
phrase like `the tag appeared as In Draft`, `status is Live`, or `the badge
shows Active` is now a first-class page-scoped assertion. It reads the visible
text of status-indicator components generically — Ant (`.ant-tag`/`.ant-badge`),
MUI (`.MuiChip`/`.MuiBadge`), Bootstrap/Chakra (`.badge`), ARIA (`role=status`),
`data-status`/`data-state`, and any `status`/`tag`/`badge`/`chip`/`pill`/`state`
-classed element — and matches the expected value (exact, then substring), with
a page-wide text fallback when a state is rendered as plain text. No selector,
no grounding. Previously such a phrase fell through to `text_visible` and
searched for the *whole sentence*, so it always failed. New
`read_status_texts()` adapter method; detection via `_looks_like_status_assertion`
and value extraction via `_extract_status_value`; or force it with
`assertion_type="status"`.

**2. Modernized Summary HTML report.** The combined summary is redesigned for
stakeholders: gradient header with a live test-pass-rate health pill, a KPI grid
(tests, pass rate, steps, self-healed, fallback, failed, duration), an inline
SVG **step-outcome donut** with legend, a **per-test breakdown** of stacked
pass/heal/fallback/fail/skip bars, and a polished detail table — all theme-aware
(light/dark) and still 100% self-contained (no external libraries or fonts).

**3. Modern console renderer (Node client).** New `formatStepLine`, `logStep`,
and a `RunConsole` tracker render each step as a clean, colorized line (status
glyph, action, resolver · confidence · timing, self-healed / ⚠ fallback flags,
and the error on failure), with a header and an enterprise-style summary footer
(counts, pass rate, elapsed). Dependency-free ANSI; auto-disables color for
non-TTY / `NO_COLOR`.

Node client `0.0.6-alpha.15` → `0.0.6-alpha.16` (`formatStepLine`, `logStep`,
`RunConsole`, `ConsoleOptions`). Adds `tests/unit/test_status_assertion.py`,
`tests/integration/test_status_verify_web.py`, and `test/console.test.mjs`.
Engine `0.0.6a68` → `0.0.6a69`.


## 0.0.6a68 — fix(web): scope input & upload resolution to the open modal

Text-entry and file-upload steps inside a modal dialog could land on a
**same-named field on the page behind the mask** instead of the modal's field.
The DOM finders searched the whole document, and while a *disabled* background
field was already avoided, a *visible, enabled* one (e.g. a workout form's
"Description" textarea behind an "Add safety disclaimer" modal that also has a
"Description") would win on DOM order — so the modal's textarea stayed empty and
the upload hit the wrong `<input type=file>`.

Both `_FIND_INPUT_JS` and `_FIND_FILE_INPUT_JS` now scope candidate collection
to the **topmost open blocking modal** when one is present (new shared
`__bgTopDialog()` helper, mirroring the existing dialog-click resolver), falling
back to the whole document when the modal holds no match — so ordinary non-modal
flows are unchanged. "Blocking" is required (aria-modal, a known component-modal
class — Ant / MUI / Chakra / Bootstrap / react-modal — or a visible backdrop),
so a non-modal `[role=dialog]` (cookie banner, popover) never hijacks fields
elsewhere on the page. Fully generic; no app- or widget-specific selectors.

Adds `tests/integration/test_modal_scope_web.py`. Engine `0.0.6a67` → `0.0.6a68`.


## 0.0.6a67 — feat(grounding): last-resort fallback selector (self-healing with a deterministic safety net)

A new opt-in safety net for enterprise suites: a tester-provided selector that
the engine uses **only after every natural + AI approach fails** to identify the
element. It keeps a critical step from red-failing on a single DOM change,
without giving up self-healing or putting selectors in the step text.

Precedence — the fallback runs dead last:

```
Tier 1 deterministic → Tier 2 fuzzy → Tier 3 AI → built-in DOM fallbacks
   → fallback_selector (NEW, last resort) → fail
```

This is deliberately distinct from the existing `selector` option, which *pins*
an element and is tried first:

  * `selector` — "use this directly" (Tier 1, unchanged).
  * `fallback_selector` (Node: `fallbackSelector`) — "try everything natural
    first; use this only if all of it fails."

Writing neither keeps the step fully selector-free. When the net catches, the
step **passes** but the result is tagged `resolver: fallback_selector` with a
`fallback_selector_used` metadata flag, a WARNING is logged, and the reports
surface it as its own signal (a purple ⚠ "Fallback" count/column in the summary
and a per-step notice in the detail report) — kept **separate from the
self-heal count** so a degraded locator strategy shows up as tech debt rather
than masquerading as healing. A fallback win is **never cached** to memory, so
the engine re-attempts natural resolution every run instead of silently pinning
the raw selector.

Accepts any Playwright locator (CSS, `xpath=…`, text engines); `data-testid` is
recommended. The Node client maps the ergonomic `fallbackSelector` alias to the
engine's `fallback_selector` for `act`/`verify`/`extract`/`recover`.

Node client `0.0.6-alpha.14` → `0.0.6-alpha.15` (`fallbackSelector` step-option
alias). Adds `tests/unit/test_fallback_selector.py` and
`tests/integration/test_fallback_selector_web.py`. Engine `0.0.6a66` → `0.0.6a67`.


## 0.0.6a66 — feat(report): multiple tests per file, kept reports, run folders, configurable summary title

Four reporting improvements, all generic and opt-in (existing single-report
runs are unchanged):

**1. Several named tests in one test file.** `report.write` gains
`scope="since_last"` (Node: `report({ scope: "sinceLast" })`). The session now
keeps a *result cursor*; a `since_last` report covers only the steps run since
the previous report, then advances the cursor. So a file can run case after
case — `report({ scope: "sinceLast", suiteName: "…", summary, html })` after
each — and every case gets its own individual report **and** its own summary
row. Default `scope="all"` reports every step, as before.

**2. Keep every individual report — no more overwrite.** A report path that
names a **directory** (ends with a separator, exists as a dir, or has no file
extension) is auto-named `<suiteName>.<ext>` inside it. Point `html`/`json`/
`junit` at a folder and per-test reports never clobber each other; the shared
`summary` keeps its own `summary.html` base name.

**3. Timestamped run folders for CI artifacts.** Any report path may contain a
`{run_id}` (or `{timestamp}`) token, expanded to a per-execution id — from
`BUBBLEGUM_RUN_ID` when set (so every test file/process in one CI run shares a
single folder) or a per-process timestamp otherwise. Write to
`reports/{run_id}/summary.html` and each execution lands in its own folder;
older runs are preserved.

**4. Configurable summary header.** The combined summary page no longer takes
its heading from whichever test happened to run last. A dedicated, persisted
`summary_title` (Node: `summaryTitle`) sets the header once and later runs don't
overwrite it; it defaults to a generic `"Test Automation Summary Report"`.
Configure e.g. `summaryTitle: "Web Automation Summary Report"`.

Node client `0.0.6-alpha.13` → `0.0.6-alpha.14` (`ReportOptions.scope`,
`ReportOptions.summaryTitle`). Adds `tests/unit/test_report_scoping_and_paths.py`.
Engine `0.0.6a65` → `0.0.6a66`.


## 0.0.6a65 — fix(core): expand dynamic tokens in action targets, not just values

A value captured earlier with `{{... as Name}}` and recalled with `{{$Name}}`
was only substituted for the **input value** of a `type`/set step. When the same
token appeared in an action **target** — e.g. `Click "Record-{{$Name}}"` to
click a freshly-created row after searching for it — the literal `{{$Name}}`
string reached grounding unexpanded. No element on the page contains that literal
text, so the click failed with low confidence and the AI tier had nothing to
match either (it, too, was searching for the raw token).

`act()` now expands dynamic tokens across the **whole instruction** up front,
exactly as `verify()` already did — so the target phrase, every quoted segment,
and the table/link/clickable resolvers all see the recalled value. Captures
(`{{timestamp as X}}`, `{{uuid:8 as Y}}`) still happen once, and value-only
expansion in `_decompose_for` becomes a harmless no-op on the already-expanded
text. Fully generic and verb-agnostic — click, hover, and every other action get
the same treatment `type` already had. Adds a regression test
(`test_click_target_expands_dynamic_token`). Engine `0.0.6a64` → `0.0.6a65`.


## 0.0.6a64 — fix(web): disambiguate a click by visible text (no selector needed)

Two controls can share an accessible name when one is named only by a decorative
icon's `aria-label`: an icon-only trigger
(`<span role="button"><span role="img" aria-label="search">`) and a real button
with visible text (`<button><icon/><span>Search</span></button>`) both answer to
`role=button[name="search"]`. A `Click the Search button` step then landed on the
first DOM match — the icon — instead of the labelled button, forcing testers to
fall back to a raw CSS `selector`, which defeats the natural-language goal.

`_do_click` now, **only when the resolved locator matches more than one element**,
picks the match whose *visible* text (its own text with `role="img"` / `.anticon`
/ `svg` / `aria-hidden` descendants removed) equals or contains the target — via
a new `_pick_click_by_visible_text` helper. It returns the original locator
unchanged for a unique match or when no candidate's visible text clearly matches,
so ordinary clicks are never disturbed; it only ever replaces an otherwise-
arbitrary first-match pick. Fully generic — no app- or widget-specific rules.

Also genericized the sample identifiers in the recently-added web integration
tests so the library carries no app-specific product terms. Adds
`tests/integration/test_click_visible_text_web.py`. Engine `0.0.6a63` → `0.0.6a64`.


## 0.0.6a63 — feat(web): click a clickable table row by its cell text

Data tables commonly make the whole **row** clickable (Ant `onRow` onClick, a
`clickable-row` class, or `cursor:pointer`) while the cell content is a plain,
non-interactive `<span>`. The interactive-element resolvers (button / link /
menuitem / `[onclick]`) never see that span, so `Click "<row text>"` — e.g.
clicking a search result in a results table — failed with no candidate.

`_FIND_CLICKABLE_JS` (the deterministic click DOM fallback) now, **only when no
interactive element matches**, looks for a clickable table row
(`tr[data-row-key]`, `tr.clickable-row`, `[role="row"]`, or a `cursor:pointer`
row) whose cell text matches — preferring an **exact** cell match so a filtered
`Row-A` row is never confused with a sibling `Row-B` that
shares its prefix, then case-insensitive, then substring. Ordinary
button/link/menu clicks are completely unaffected (the row scan runs only after
the interactive search finds nothing).

So `Click "<name>"` (or `Click the "<name>" text in the table`) now clicks the
row — which matters because the name is usually a dynamic `{{…}}` value that must
be expanded in the instruction (a static `selector` can't carry it). Adds
`tests/integration/test_clickable_row_web.py`. Engine `0.0.6a62` → `0.0.6a63`.


## 0.0.6a62 — feat(web): `select_no_filter` — pick a dropdown option without type-to-filter

New opt-in per-call option for `select` steps. Searchable comboboxes are
normally resolved by typing the value to filter the list, but some Ant selects
key their options by an **id/GUID** (the option *value*) and only *display* a
friendly label. Ant filters by the value, so typing the label filters against the
GUID and **empties the list** — the option can never be clicked (symptom: "type
the text and the items disappear"). Passing `select_no_filter: true` skips the
typing and instead **scans the open list, scrolling a virtualized popup as
needed**, then clicks the option by its visible text:

```ts
await bg.act('Select "My Item" from the Item dropdown', { select_no_filter: true });
```

Threaded from `ExecutionOptions.select_no_filter` (default `false`) through
`_do_select` → `_select_from_custom_combobox` → `_select_single` →
`_try_pick_option`, which now guards the type-to-filter block and adds a bounded
virtual-list scroll-scan (`_scroll_open_list_to_option`). The default select path
is **unchanged** — every existing dropdown behaves exactly as before. Adds
`tests/integration/test_select_no_filter_web.py` (default types-and-fails vs
opt-in scans-and-selects) and a `build_options` plumbing unit test.

Engine `0.0.6a61` → `0.0.6a62`.


## 0.0.6a61 — fix(web): stop text values piling into the first input on unlabeled forms

On a form whose Ant inputs have no accessible name — the labels use `for=` ids
the inputs don't carry (only `data-testid`), so the label↔input link is broken —
every `Enter "X" into <field>` step landed in the **first** input. Three distinct
causes, all fixed:

1. **Nameless `role=textbox` silently filled `.first`.** With no accessible name,
   grounding produced a bare `role=textbox` that matches every input; the
   executor's strict-mode fallback then filled the first match. The `.first`
   strict-mode fallback is now disabled for value-entry actions (`type`/`fill`/
   `set`) — it re-raises so the label-based DOM input resolver can target the
   real field. (It still applies to clicks, where first-match is reasonable.)
2. **The LLM tier returned a nameless `role=` ref.** `_parse_response` now
   discards any `role=<role>` ref without a `[name="…"]` — ambiguous by
   construction — so the deterministic label resolver takes over instead.
3. **`find_input` fell back to the first input on no match.** The DOM-order
   tie-break made an unmatched phrase score just above zero, so it returned the
   first field. It now requires a genuine label/placeholder/section match, and
   matches whitespace-insensitively so a spaceless phrase (`FieldThree`)
   still resolves its spaced label ("Field Three").

Net: each value goes to its own field, and a field that genuinely can't be
resolved fails loudly instead of silently filling the wrong box. Adds
`tests/integration/test_nameless_inputs_web.py` (browser-backed) and a
nameless-role parser unit test. Engine `0.0.6a60` → `0.0.6a61`.


## 0.0.6a60 — fix(web): don't undo a committed multi-select value during self-correction

A multi-select step could log `passed` while the value ended up **not** selected
(the option briefly committed, then vanished; the dropdown was left open). Root
cause is in `_select_single`'s self-correcting probe: grounding resolves the
field to its inner `role=combobox` `<input>`, while `_other_select_triggers`
returns that same input's `.ant-select` **container** as a separate "other"
candidate. The value is committed on the input, then the post-commit cleanup —
which exists to undo a stray selection left on a *wrongly-probed different*
combobox — sees the same widget's brand-new tag, treats it as stray, and clicks
its × to remove it. Net result: success reported, nothing selected. It only bit
real Ant widgets (whose selection tag has a working × remove control); simpler
mimics with a non-functional × masked it.

`_select_single` now dedupes its candidate list by the underlying `.ant-select`
widget (new `_dedupe_select_candidates`, keyed on a stable per-widget DOM
expando, order-preserving so the resolved trigger is still tried first), so a
widget is never both the commit target and a cleanup target. A genuinely
different combobox is still probed and still cleaned up.

Adds a browser-backed regression (a functional × remove control + the inner
`role=combobox` ref) to `tests/integration/test_multiselect_label_commit_web.py`.
Engine `0.0.6a59` → `0.0.6a60`.


## npm 0.0.6-alpha.13 — fix(node): run the engine from the active virtualenv

The Node client spawned the bridge as bare `python -m bubblegum.bridge`, resolved
against the Node process's `PATH`. When a tester `pip install`ed the engine into
an activated venv but the Node runner's `PATH` didn't point at that venv (common
with IDE test runners, `npx`, or a shell that didn't re-activate), the bridge
silently ran a *different*, often older, engine than the one just installed — so
engine fixes appeared to have no effect (the handshake's `engine_version` /
"BRIDGE ENGINE" line reported the stale version).

`spawnBridgeTransport` now resolves the interpreter via a new exported
`resolveBridgeCommand(env)`:

1. `BUBBLEGUM_PYTHON` — explicit override, always wins.
2. the active virtualenv (`VIRTUAL_ENV`) interpreter, when it exists on disk —
   so "install into the venv" and "the bridge runs" are the same Python.
3. `python` — the previous `PATH`-resolved default (graceful fallback, incl. a
   stale `VIRTUAL_ENV`).

Per-call `spawn: { command }` still overrides everything. Engine unchanged;
npm client `0.0.6-alpha.12` → `0.0.6-alpha.13` (adds 4 `resolveBridgeCommand`
unit tests; full client suite green, typecheck clean).


## 0.0.6a59 — fix(web): verify multi-select commit even when the field is grounded to its label

A multi-select step could log `passed` while nothing was actually selected. The
"did the click add a selection tag?" verification (`_value_committed`) only ran
when the *resolved trigger element* was itself inside `.ant-select`
(`_is_ant_select`). Grounding often resolves a field by its label text and lands
on the `<label for=…>`, which sits **outside** the widget — so verification was
skipped and a click that never committed was reported as a successful select.
This showed up on Ant Design `ant-select-multiple` fields (e.g. a "Related
domains" picker) whose option row carries no `title` attribute and whose visible
label lives in a nested `<span>`.

The adapter now resolves the *associated* `.ant-select` widget from the trigger
via a shared `_ANT_ROOT_JS` helper — self / ancestor / descendant / the
`label[for]` the trigger is or sits inside — and both `_is_ant_select` and
`_selected_texts` climb to that root. Result: a click that genuinely commits is
verified and passes; a click that does not commit is now correctly reported as a
failure instead of a false pass, regardless of whether grounding resolved the
widget or its label. Added `tests/integration/test_multiselect_label_commit_web.py`
covering the label-resolved non-commit (must fail), label-resolved commit (must
pass), and in-widget non-commit (must fail) cases.

Engine `0.0.6a58` → `0.0.6a59`.


## 0.0.6a58 — chore: replace app-specific sample identifiers with generic placeholders

Documentation, tests, example fixtures, and changelog history referenced
identifiers from a specific application under test. These carried no behavior —
they were only sample data — and have been replaced throughout with neutral
placeholders (generic app/label names, `RecordID` table columns, `appium.example.com`
hosts, `Continue` labels, etc.). The project-specific mobile pilot doc was
removed and replaced by a generic guide,
`docs/mobile-attach-existing-session.md`. No API, resolver, or runtime behavior
changes; the full suite and the TS client tests pass unchanged.

Engine `0.0.6a57` → `0.0.6a58`; npm client `0.0.6-alpha.11` → `0.0.6-alpha.12`.


## 0.0.6a57 — fix(mobile): exact-label preference so "Allow" wins over "Don't Allow"

Follow-up to a56, for iOS system permission alerts (e.g. the notifications
"Allow" / "Don't Allow" dialog). Both buttons contain the substring "allow", so
the bidirectional substring match returned both as equal-confidence candidates —
risking a tap on the wrong one (denying the permission).

- **The mobile resolver now scores match exactness.** An exact label match keeps
  full confidence (text 0.92 / accessibility 0.85); a looser partial match is
  eased down proportionally to how much extra text surrounds the hit, so the
  exact "Allow" outranks the partial "Don't Allow". A leading action verb is
  stripped first ("Tap Login" scores as an exact match of "Login"), matching the
  parser's target-phrase decomposition. Both buttons stay resolvable — asking for
  "Don't Allow" by its exact label still selects it — and Android matching is
  unchanged. The chosen `match_quality` is surfaced in candidate metadata.

Engine-only change; no TS client change (the npm `attachMobile` from
`0.0.6-alpha.11` is unaffected). Engine `0.0.6a56` → `0.0.6a57`.


## 0.0.6a56 — feat(mobile): iOS (XCUITest) grounding + attach to an existing Appium session

Enables the mobile pilot: resolving iOS elements by human text, and running an
in-test Bubblegum fallback against a cloud device (pCloudy / BrowserStack) where
only one Appium session per device is allowed.

- **iOS attribute matching in `AppiumHierarchyResolver`.** The mobile Tier-1
  resolver previously read only Android UiAutomator2 attributes
  (`text` / `content-desc` / `resource-id` / `bounds` / `visible-to-user`), so
  grounding by text returned no candidate on iOS. It now reads XCUITest
  attributes too and maps both platforms onto one view: iOS `label` → visible
  text, `name` → accessibility id, `value` → field value, `type` → widget type,
  and x/y/width/height → the Android-style `bounds` string used for visibility
  scoring. XPaths are built with the right per-platform attribute
  (`//XCUIElementTypeButton[@label='Continue']`). This fixes the
  common React-Native-iOS case where a `testID` becomes the XCUITest `name` but
  the visible label is what a human (and Bubblegum) matches on — so a text/predicate
  locator fails while `act("Tap Continue")` succeeds. Android matching
  is unchanged.
- **Attach to an existing Appium session (`channel.mobile.attach`).** New
  `existing_session_id` on `session.open` and `Bubblegum.attachMobile({ appiumUrl,
  existingSessionId, capabilities })` in the TS client let the engine reuse the
  Appium session another test (e.g. WebdriverIO) already drives, by its
  `browser.sessionId`, instead of opening a second one. The engine shares the
  live session and **never quits it** — the host test keeps ownership of
  teardown, so `bg.close()` tears down only the engine wrapper. Backed by
  `attach_to_appium_session()`, which binds an Appium `Remote` to the existing
  id by intercepting the `newSession` command.

Engine `0.0.6a55` → `0.0.6a56`; npm client `0.0.6-alpha.10` → `0.0.6-alpha.11`.


## 0.0.6a55 — feat(report): one combined report — Summary tab + per-test collapsible details

Follow-up to the a54 summary. Instead of a separate summary file plus a
single per-session detail report (which showed only the last test), the
``summary`` report is now ONE combined, self-contained HTML with two tabs:

- **Summary** — every test with pass / self-healed / fail / skip counts + grand
  totals (as before).
- **Test details** — one collapsible ``<details>`` per test, each embedding that
  test's full step-by-step report (the same content as the standalone
  ``bubblegum-report.html``, screenshots included) inside an isolated
  ``<iframe srcdoc>`` so each test's styling/scripts cannot collide.

Each run writes its full detail HTML into a sibling ``<name>.d/`` directory and
upserts its row in the ``<name>.json`` manifest, so the combined report is
rebuilt from every recorded test — not just the last process's. Re-running a
test replaces its row and detail. No new API surface: still driven by
``report({ summary, suiteName })`` / the bridge ``report.write`` ``summary`` param.

Engine `0.0.6a54` → `0.0.6a55`; npm client `0.0.6-alpha.9` → `0.0.6-alpha.10`.


## 0.0.6a54 — fix(log): quiet the "Execution failed" line on recovered steps; feat(report): cross-run suite summary

Two reporting/observability improvements from real-app feedback.

- **Recovered steps no longer log a scary "Execution failed" ERROR.** When a
  step's first execution fails but the SDK then recovers it (custom select /
  modal field via a DOM handler), the adapter used to log
  `Execution failed for ref=…` at ERROR *before* the recovery decision — so a
  step that ultimately PASSED looked failed in the log. That per-attempt line is
  now DEBUG; the authoritative outcome is the step result (`recovered`/`failed`),
  and a genuine, unrecovered failure still carries the full error in its
  StepResult (surfaced by the caller/report). No detail is lost.
- **Cross-run suite summary report.** Reports are written per session (per
  process), so running several tests each in their own process and writing to
  the same paths left only the last one. New `summary` report option upserts
  each run (keyed by `suiteName`) into a sibling `*.json` manifest and renders an
  aggregated HTML overview: every test with its pass/self-healed/fail/skip
  counts, plus grand totals (tests run/passed/failed, total steps). Re-running a
  test replaces its row. Available via the bridge `report.write` `summary` param
  and the TS client `report({ summary, suiteName })`.

Engine `0.0.6a53` → `0.0.6a54`; npm client `0.0.6-alpha.8` → `0.0.6-alpha.9`.


## 0.0.6a53 — fix(web): don't type into a disabled same-named field behind an open modal

Follow-up to a52, for the popup-input flake reported on the "Add a Product"
modal. Typing into the modal's `Points` field filled nothing and timed
out because grounding matched a **disabled** same-named spinbutton
(`id="budgetField"`) on the page *behind* the modal — Playwright's `.first` picks
the earlier-in-DOM element, and it can never be typed into.

- **`find_input` now excludes disabled/readonly inputs.** Its JS filtered by
  visibility but not by enabled-state (contradicting its own "visible, enabled"
  contract), so a disabled twin could win. It now skips `disabled` / `readOnly`
  / `aria-disabled="true"` elements. Verified in a real browser against the
  reported DOM (disabled `budgetField` behind the modal + enabled `pointsField`
  inside it → the enabled modal field is chosen).
- Combined with a52's execution-failure recovery, a `type` step that grounds to
  a disabled twin now recovers to the modal's real field and caches it.

Not changed: the ambiguous `Click "Done"` step (13 whole-page candidates) —
that is grounding ambiguity best resolved with a more specific phrase or a
dialog-scoped click handler; tracked separately.

Engine `0.0.6a52` → `0.0.6a53`; npm client `0.0.6-alpha.7` → `0.0.6-alpha.8`.


## 0.0.6a52 — fix(web): recover custom-select steps the AI tier grounded but couldn't execute

Fixes a flake introduced by wiring the AI grounding tier in a51. On custom
`role=combobox` selects (Ant Design / MUI / CDK) whose real accessible name
differs from their visible label, `llm_grounding` can return a confident-looking
ref like `role=combobox[name="Recommendation Tags"]` that does not actually
resolve on the page — so `select_option` (or the locator wait) times out. The
deterministic DOM select-trigger handler that used to catch these only ran when
*grounding* raised, not when grounding succeeded and *execution* failed, so the
step failed intermittently (it passed whenever the DOM handler or memory cache
won the race instead).

- **Execution-failure recovery.** When a grounded target resolves but fails to
  execute, the deterministic DOM handlers (select-trigger, clickable, input) are
  retried once; if one executes, the step is **recovered** and the working ref
  is cached, so the next run resolves it directly (killing the flake). This runs
  **only on failure**, so every currently-passing step is untouched. Web only,
  best-effort, never raises. New `tests/unit/test_execution_failure_recovery.py`.

Engine `0.0.6a51` → `0.0.6a52`; npm client `0.0.6-alpha.6` → `0.0.6-alpha.7`.


## 0.0.6a51 — feat: AI grounding overhaul — accuracy, speed, cost, enterprise

A focused pass to make the AI layer effective, faster, cheaper, and
enterprise-ready. Every new capability is **dormant/off by default** and
**backward-compatible** — existing configs behave exactly as before. Unit suite
1913 → **1979** passing. See `docs/ai-grounding-enhancements.md` for setup and
how to test against a real app.

- **AI grounding tier is now actually wired.** The Tier-3 LLM grounding resolver
  was registered with no provider, so the documented "AI when deterministic
  resolvers fail" fallback never fired in production. It is now wired from
  config (best-effort; dormant when `ai.model` is unset), and text grounding is
  reclassified `high → medium` so it is reachable under the default cost policy.
  A successful AI resolution is persisted as a **durable** locator to the SQLite
  memory cache and replayed as a Tier-1 hit (zero model calls) next run.
- **Prompt caching + tiered model routing.** `ai.fast_model` / `ai.strong_model`
  (grounding uses fast; escalates to strong only when unsure, opt-in via
  `escalate_on_low_confidence`), provider-native prompt caching, reused clients,
  configurable `ai.max_tokens`.
- **Guaranteed-schema structured output.** OpenAI Structured Outputs / Anthropic
  tool-use replace the brittle "reply in JSON" + fence-stripping, eliminating
  silent parse failures. Graceful fallback for models without support.
- **Semantic (embedding) Tier-2 resolver.** Catches meaning-level label drift
  ("Submit"→"Continue") before the LLM tier. Pluggable embeddings (OpenAI
  built-in; offline/self-hosted via `configure_embedding_provider`), cached.
  Activated by `ai.embedding_model`.
- **Async resolver contract.** The engine awaits resolvers; the LLM call runs
  natively on the event loop instead of a throwaway thread + event loop.
- **Pluggable screenshot-grounding backend, first-class on mobile.**
  `grounding.vision_backend` = none | anthropic | openai | http | callable. The
  `http` backend targets a **self-hosted** grounder (OmniParser / UI-TARS) so
  screenshots stay in-network (`privacy.vision_is_local`); it normalizes
  candidate / set-of-mark / point responses. Coordinate refs are never cached.
- **Resilience + config-driven pricing.** Per-call hard timeout + bounded
  retry/backoff on transient errors (`ai.timeout_ms` / `max_retries` /
  `retry_backoff_ms`); `ai.pricing` overrides the built-in cost table without a
  release. Shared provider plumbing consolidated (single `strip_code_fence`).
- **Streaming observability + replay mode.** Per-step structured observations to
  a pluggable sink (`observability.export` = jsonl | otel | both; OTel is a
  no-op when the SDK is absent). `grounding.ai_mode: replay` resolves only from
  the learned cache + deterministic tiers for zero-cost, deterministic CI.
- **Code generator paused.** `bubblegum record` and `bubblegum convert` are in
  maintenance mode (docs + `--help` note); no code/CLI changes — bug fixes only.

Engine `0.0.6a50` → `0.0.6a51`; npm client `0.0.6-alpha.5` → `0.0.6-alpha.6`.


## 0.0.6a50 — fix(web): named-panel dropdown wins over already-selected twin; option-scoping

Follow-up to a49. `Select … from "Drink Bonus Type" drop down` still committed into
the **Food** panel once the Food "Bonus Type" had already been set. Two distinct
bugs, both fixed generically (no page-specific strings; works for any number of
panels and other apps):

- **The panel qualifier is now decisive.** Ant gives a select that already displays
  the wanted value a large "shows the value" bonus, which was outscoring the Drink
  panel — so the Drink step re-picked the already-set Food select. The select finder
  now detects when the step names a panel that exists on the page and strongly
  prefers a control in that panel while demoting controls in a *different* named
  panel, overriding the already-shown-value bonus. No panel named ⇒ no effect, so
  ordinary single-panel forms are untouched.
- **Option clicks are scoped to the dropdown the trigger owns.** Even with the right
  (Drink) trigger, the option-selection searched the whole page for an option row
  matching the value; with "Test Basket" present in both the Food (already-selected)
  and Drink dropdowns, the first-in-DOM (Food) row was clicked. The click is now
  scoped first to the popup the resolved combobox owns (via `aria-controls`/`owns`
  → its `.ant-select-dropdown`), so the value can only land in the resolved select.
- Coverage: `tests/unit/test_sectioned_fields_rewards.py` gains an interactive
  two-panel case (Food pre-selected with the value; the Drink step still commits to
  Drink). Browser-verified end-to-end. Engine `0.0.6a49` → `0.0.6a50`.


## 0.0.6a49 — fix(web): panel-name qualifier for repeated dropdowns across accordions

Follow-up to a48. On the Bonus Gamification page, `Select … from "Drink Bonus
Type" drop down` still landed in the **Food** panel's dropdown: the "Bonus Type"
select carries neither "bonus" nor "type" in its id, and its column header is
shared across both panels, so Food-vs-Drink rested on one weak (0.5-weight) id
token and Food edged ahead in the live DOM.

- **Collapse/accordion panel headers are now a first-class section signal.** The
  shared section detection also reads the header of any enclosing collapsible panel
  (Ant `.ant-collapse`, MUI `Accordion`, any `[aria-expanded]` disclosure), so a
  field that repeats across like-structured panels is disambiguated by the **panel
  name** the tester writes — not by whether the panel name happens to appear in an
  id. Fully generic: works for one panel, many panels, or none (no panel ⇒ no
  effect), and for any labels, so it is not tied to "Food"/"Drink".
- **Dropdown finder weights the panel name.** `Select "2" from "Drink Stamp
  Position"` / `"Drink Bonus Type"` now resolve to the Drink panel with a
  comfortable margin (~0.8) instead of a coin-flip (~0.17). Ordinary dropdowns not
  inside an accordion are unaffected.
- **Dropdown selector is now stable.** The select finder returns an id-keyed
  selector (e.g. `.ant-select:has([id="…"])`) instead of the wipe-prone
  `[data-bg-select]` marker, matching the radio/checkbox/input resolvers, so a
  React re-render between resolution and the open-click can't retarget it.
- Coverage: `tests/unit/test_sectioned_fields_rewards.py` gains a two-panel case
  (Drink/Food qualifier lands in the right panel + column). Verified end-to-end
  against the real captured page DOM. Engine `0.0.6a48` → `0.0.6a49`.


## 0.0.6a48 — fix(web): placeholder-only fields & shared column-header dropdowns

Follow-up to a47 on the same Rewards/Gamification page. Two controls were still
resolving to the wrong twin; both fixes are generic (geometry / id / placeholder,
no page-specific strings).

- **Number field with only a placeholder now disambiguates by section.** A
  "Stamp Position" range input (visible label is a bare `<span>`, the only
  accessible name is the placeholder "Position") exists in both a Food and a Drink
  panel. Because it had no `<label>`, the input finder saw it as "unique", the step
  fell to the a11y snapshot (which has no section context), and
  `Enter "2" into Rewards Drink Stamp Position` overwrote the **Food** field. The
  finder now folds the placeholder into its collision test, so the two like-placeholdered
  fields register as a genuine collision, the step is flagged `sectioned`, and the
  pre-resolver pins the right one by its id/section. The input selector is now a
  **stable id** (`#…`) rather than a marker, matching the radio/checkbox resolvers.
- **Dropdowns under a shared column-header row.** "Stamp Position" and "Bonus Type"
  label two side-by-side selects through a single header row, so the finder read the
  whole row and both columns tied — `Select … from "Bonus Type" drop down` grabbed
  the Stamp Position select and then failed (no such option). A geometry-based
  **column heading** now labels each select by the header cell horizontally above
  it, so "Bonus Type" resolves to its own (basketName) select. Fires only when such
  a header row exists; ordinary single-label dropdowns are unaffected.
- Coverage: `tests/unit/test_sectioned_fields_rewards.py` (Drink number field
  doesn't overwrite Food; "Bonus Type" resolves to its own column). Browser-verified
  end-to-end against the real captured page DOM. Engine `0.0.6a47` → `0.0.6a48`.

  Step-writing note: for the second Bonus row (after expanding Bonus → Drink), keep
  the `Drink` qualifier — `Select "2" from "Drink Stamp Position" drop down` and
  `Select "Test Basket" from "Drink Bonus Type" drop down` — since both Food and
  Drink dropdowns are then visible and share the same column labels.


## 0.0.6a47 — fix(web): expand the right accordion panel; section-aware dropdowns

Targets a Rewards/Gamification page where the same label repeats across sections
and inside default-collapsed accordion panels. All fixes are generic (no page- or
label-specific hard-coding) and additive over a46.

- **Expand/collapse a named panel — new resolver.** A step like
  `Click on "Drink" button to expand Drink section` now resolves the Ant
  `.ant-collapse-header` (MUI `AccordionSummary` / any `[aria-expanded]` toggle)
  by its panel label **plus** the surrounding section words, instead of the
  generic clickable path that tied on "Drink" and always clicked the first one in
  DOM order — which made expanding the Bonus panel re-click (and collapse) the
  Rewards one. Two like-named panels are told apart by their section heading
  (`… in Bonus Gamification`). The selector is **stable** (pinned via a
  panel-body element id with `:has()`, so a React re-render can't retarget it) and
  the expand/collapse is **idempotent** — an already-open panel is a no-op, never
  toggled shut. Gated on the word "expand"/"collapse"/"accordion" so ordinary
  clicks are untouched.
- **Section-aware dropdown disambiguation.** The select-trigger finder now adds a
  bounded section/id-context tiebreak (the same pattern the radio/checkbox/input
  resolvers use). Two identically-labelled selects in different panels
  (`Stamp Position` under a Food vs a Drink panel) are told apart by the
  `food`/`drink`/section word that only appears in the right control's id —
  `Select "2" from "Drink Stamp Position" drop down` now lands on the Drink one.
  Additive and bounded (weight 0.5), so it can't override which dropdown the label
  points at; full suite unchanged.
- **Section-labelled number fields & repeated checkboxes** (already handled by the
  a44–a45 id/section machinery) now resolve correctly once the owning panel is
  expanded: `Enter "1" into Food Stamp Position`, `Enter "2" into Rewards Drink
  Stamp Position`, and `Select "Reset metric daily" checkbox for Food` / `… for
  Drink` each pin the right control by its section context.
- Coverage: `tests/unit/test_collapse_expand.py` (two like-named panels expand
  independently; idempotent expand). Browser-verified against the real captured
  page DOM. Engine `0.0.6a46` → `0.0.6a47`; npm client unchanged.


## 0.0.6a28 — feat(convert): manual test scenario → automation converter

Adds the `bubblegum convert` command and `bubblegum.convert` package on top of
the a27 runtime: Excel scenarios → smart-tests TypeScript (flows + tests + data
+ harness) with project wiring, data extraction, multi-sheet, cleanup, dedup,
and validation. Purely additive over a27 (no core changes). New optional extra:
`pip install "bubblegum-ai[convert]"`. Engine 0.0.6a27 → 0.0.6a28; npm client
unchanged. Full suite 1941 passed; generated TypeScript type-checks under tsc.


## 0.0.6a27 — fix(verify): page-appearance asserts, dynamic tokens in verify, multi-column rows

- **"the X page appear" now asserts the heading.** `verify("the Create Badge page
  appear")` reduced to searching the page for that whole sentence (not found).
  `extract_expected` now strips a leading article and trailing appearance verbs
  (`appear`/`appears`/`loaded`/`opens`/…) and a dangling `page`, so it checks for
  "Create Badge" — the visible heading. Existing `... is visible` behaviour kept.
- **Dynamic tokens now expand in `verify`.** `{{$name}}` recalls (and `{{today}}`,
  `{{timestamp}}`, …) are substituted in the assertion — so you can validate a row
  that contains a value generated earlier in the run
  (`verify('in the row where Badge Internal Name is "{{$badgeInternalName}}", …')`).
  Applied to the phrase and to `expected_value` / `row_match` / `cell` kwargs.
- **Multi-column row assertions.** `in the row where <key> is "X", <colA> is "A",
  <colB> is "B"` now checks *every* listed column (previously only the first cell
  parsed; the rest were swallowed into one value). Quote-aware splitting keeps a
  value that contains a comma intact, and a trailing "… is visible" is tolerated.
- Coverage: `tests/unit/test_verify_page_and_rows.py`; browser-verified against a
  Badges-style table with token recall. Engine `0.0.6a26` → `0.0.6a27`.

## 0.0.6a26 — feat(web): radio selection + checked-state verification

- **Select a radio by label.** `Select/Choose/Click "<label>" radio [button]` now
  resolves the radio deterministically and clicks its wrapper/label — fixing Ant
  (and MUI) radios where the real `<input type=radio>` is hidden (`opacity:0`)
  behind a styled wrapper, so name grounding missed it and the step wrongly fell
  to the dropdown resolver (`select_trigger_dom`) without actually selecting
  anything. New resolver `radio_dom`; the `select` verb is coerced to a click
  (selecting a radio == clicking it). No-op on pages without a radio.
- **Verify a radio's state.** `verify("<label> radio is selected")` (and
  `is not selected` / `checked` / `unchecked`) reads the control's real checked
  state — the previous `element_state` assertion only checked visibility. Works
  for native, Ant and MUI radios.
- Verified end-to-end against a real Ant `Radio.Group` (selection sets the value;
  positive/negative assertions pass/fail correctly). Coverage:
  `tests/unit/test_radio_fallback.py`. Engine `0.0.6a25` → `0.0.6a26`.

## 0.0.6a25 — feat(web): dialog-scoped clicks + named capture/recall of dynamic values

- **Confirmation dialogs.** A click/tap now prefers the button **inside the
  topmost open modal** (Ant confirm, `[role=dialog]`, native `<dialog>`, common
  modal classes). Previously `Click Submit` on a "Submit Badge?" confirm resolved
  to the *page's* Submit behind the mask and hung ("…intercepts pointer events").
  New pre-grounding resolver `dialog_click_dom` splits an `... on <title> dialog`
  scope tail off the label and matches within the dialog. No-op when no dialog is
  open. Verified end-to-end against a real Ant `Modal.confirm` (Submit / "No,
  cancel" both route correctly).
- **Remember a generated value and reuse it later.** Append `as <name>` to a
  dynamic token to store its value, then recall it with `{{$name}}` in a later
  step — so a unique value you generate can be reused to search/validate the same
  record:

      act('Enter "Badge_{{timestamp|%Y%m%d%H%M%S as badgeName}}" into Display Name')
      # ...later...
      act('Enter "Badge_{{$badgeName}}" into Search')
      verify('{{$badgeName}} is visible')

  The store is per engine session, so reuse across steps works through the Node
  client with no protocol change. Read it from Python via `bubblegum.variables()`
  / `recall(name)`; seed or reset with `remember(name, value)` /
  `clear_variables()`. Unknown `{{$name}}` recalls are left verbatim.
- Coverage: `tests/unit/test_dialog_click_fallback.py`, capture/recall cases in
  `test_dynamic_value_tokens.py`. Full unit suite 1864 passed. Engine
  `0.0.6a24` → `0.0.6a25`.

## 0.0.6a24 — fix(parser): a verify cue word in a field label no longer hijacks the action

- `Enter "…" into Description shown when viewing an Earned Badge` was
  misclassified as **verify** (then failed at execute with "Unsupported
  action_type … verify") because the field label contains "shown" — one of the
  verify cue words (`visible`/`present`/`displayed`/`shown`). The cue scan ran
  over the whole instruction, including the target name.
- The **leading action verb now wins**: when an instruction starts with an
  explicit verb (`Enter`/`Type`/`Fill`/`Select`/`Click`/…), that owns the intent,
  and verify cues appearing later in the target are ignored. The verify-cue scan
  still catches verb-less phrasing ("login is visible"), and `Check that/if/whether …`
  still resolves to verify. This unblocks typing into `textarea`s (and any field)
  whose label happens to contain a state word — resolved via the existing
  `input_dom` fallback once the action is correctly `type`.
- Coverage: regression cases in `tests/unit/test_instruction_decompose.py`;
  browser-verified against the Acme "Description shown when viewing an Earned
  Badge" / "… when the Badge is awarded" textareas. Engine `0.0.6a23` → `0.0.6a24`.

## 0.0.6a23 — feat(web): resolve hidden file inputs for `upload` steps (multi-section)

- `Upload "<path>" into <target>` now resolves the real `<input type=file>` even
  when it's **hidden** behind a styled button (Ant/MUI `Upload`), which the a11y
  tree and the visible-input fallback can't reach. New pre-grounding resolver
  `file_input_dom` scores every file input by its form-item label, **nearest
  section heading**, and id/name/testid (camelCase + kebab split into words).
- Handles **multiple upload widgets on one page** with repeated labels: name the
  section in the phrase to disambiguate, e.g. `Upload "..." into Awarded Album
  View` vs `... into Upcoming Album View` (the six Album/Front/Back × Awarded/
  Upcoming uploaders on the Acme Create-Badge page all resolve uniquely).
- Scoped and safe: only fires for `upload` steps that name a target, and is a
  no-op on pages with no file input. Verified end-to-end against a **real Ant v5
  `Upload`** (file registers in antd's list). Coverage:
  `tests/unit/test_upload_fallback.py`. Engine `0.0.6a22` → `0.0.6a23`.

## 0.0.6a22 — fix(web): commit typed value into date/time picker inputs (Enter)

- Typing into a date/time picker input now **activates and commits** the field
  (click → fill → Enter) instead of a bare `fill()`. Ant `RangePicker` keeps
  "active editing" on one field until Enter, so a plain fill sent the *end* value
  into the *start* input (both range values landed in "Start date", e.g.
  `06/07/2026 07:0016/07/2026 23:59`). With the commit keystroke, start and end
  each land in their own field.
- Detected generically (no per-app selectors): the input is inside `.ant-picker`
  / a `*[class*="DatePicker"|"datepicker"|"TimePicker"|"MuiPickers"]` widget, or
  carries a `date-range` attribute. Ordinary text inputs keep the plain `fill()`
  path — no stray Enter, so form submits aren't triggered.
- Verified end-to-end against a **real Ant v5 `RangePicker`** (React + antd UMD),
  not just static markup. Coverage: `tests/unit/test_picker_type_commit.py`.
  Engine `0.0.6a21` → `0.0.6a22`; npm client unchanged.

## 0.0.6a21 — fix(web): deterministic resolver for date-range picker start/end inputs

- `type "…" into Start date` / `End date` now pins the exact input of an Ant
  `RangePicker` from the DOM **before** name-based grounding runs, instead of
  letting a nameless picker input (no id/label/aria — only a `date-range`
  attribute or a "Start date"/"End date" placeholder) get mis-matched to some
  other "date"-ish element on the page. The phrase's side word (`start`/`from`/
  `begin` vs `end`/`until`/`finish`) selects which input; when a page has more
  than one range picker, the form-item label breaks the tie. New resolver
  `date_range_dom` (confidence 0.9).
- Scoped and safe: only fires for `type`/`fill` steps whose phrase names a side,
  and is a **no-op on pages without a range picker**, so ordinary text fields are
  unaffected (they keep resolving via the a11y tree / `input_dom` fallback).
- Coverage: `tests/unit/test_date_range_fallback.py`; validated against the real
  Acme Create-Badge "Visibility Period" range picker markup. Engine `0.0.6a20` →
  `0.0.6a21`; npm client unchanged.

## 0.0.6a20 — feat: absolute time-of-day in date tokens (`@HH:MM`); consolidates a18+a19

- Dynamic-value date tokens gain an **`@` absolute-time setter** so you can pin a
  computed date to a specific clock time instead of midnight or "now shifted":
  - `{{today+2d@07:00|%d/%m/%Y %H:%M}}` — 2 days out, at 07:00.
  - `{{tomorrow@9am|%d/%m/%Y %H:%M}}` — accepts `9am` / `9:30pm` / `23:59` /
    `07:00:00`. Applied after any date offset. When `@` is present and no `|`
    format is given, the default format includes the time (`%Y-%m-%d %H:%M`).
- Consolidation release: this is the first version published from `main` that
  contains **both** the uniqueness tokens (`{{timestamp}}`/`{{uuid}}`/`{{random}}`,
  originally `a18`) and the `a19` web clickable-fallback fix. `a18` was never on
  `main` and `a19` was cut from `a17` without the tokens; `a20` merges both so
  `pip install -U bubblegum-ai` gets every feature. Engine `0.0.6a19` → `0.0.6a20`.

## 0.0.6a18 — feat: uniqueness dynamic-value tokens ({{timestamp}}, {{uuid}}, {{random}})

- Dynamic-value tokens now cover **run-time uniqueness**, not just relative
  dates, so a field with a unique constraint (a badge name, an email, any
  create-form value) can be parameterised inline instead of hard-coded:
  - `{{timestamp}}` — Unix epoch seconds; `:ms` for milliseconds, or a `|`
    strftime for a readable stamp, e.g. `Badge_{{timestamp|%Y%m%d%H%M%S}}`.
  - `{{uuid}}` — random uuid4 hex (32 chars); `:N` keeps the first N chars
    (`{{uuid:8}}`). Unique regardless of the clock.
  - `{{random}}` — N random digits, default 6 (`{{random:6}}`).
- Same engine-side substitution path as the date tokens (`_decompose_for` in
  `sdk.py`), so it works identically for the Python SDK and the Node client
  across web, mobile, and CDP-attach. Malformed arguments and unrecognised
  tokens are left verbatim; literal values are untouched.
- Coverage: extended `tests/unit/test_dynamic_value_tokens.py`. Documented in
  `docs/USER_GUIDE.md`, `docs/HOW_TO_USE_TYPESCRIPT.md`, and the Node README
  (this fills a gap — the date tokens were previously undocumented in the guide).
  Engine `0.0.6a17` → `0.0.6a18`; npm client unchanged (engine‑side feature).
=======
## 0.0.6a19 — fix(web): clickable fallback strips trailing widget nouns

- `Click the <X> menu` (and `button`/`link`/`tab`/`option`/`item`/`field`) now
  resolves the control named `<X>` via the DOM clickable fallback: when the exact
  phrase doesn't match, it retries with the trailing widget word removed. Fixes
  `Click the Badges menu` matching the `Badges` nav item whose accessible name is
  just "Badges". (Only helps when the item is actually visible — an item hidden
  in an Ant `...` overflow menu must be reached by clicking the overflow first.)
- No parser behaviour change (the "X menu" target phrase is preserved, as some
  controls are literally named "… menu"). Note: `0.0.6a18` on PyPI was **not**
  published from this repository's `main` — this is the next release from `main`
  after `a17`. Engine `0.0.6a17` → `0.0.6a19`; npm unchanged.

## 0.0.6a17 — fix(web): DOM input fallback for nameless text fields

- `type`/`enter` into a field with **no accessible name** (e.g. a `<textarea>`
  whose `<label for=...>` points at a missing id — like the Acme "Remarks"
  field) now resolves via a DOM fallback that scores visible, enabled
  inputs/textareas by associated label / placeholder / nearby form-item label
  against the target phrase. Ant-select search inputs and disabled fields are
  excluded. Same proven pattern as the select / click / link / table fallbacks.
- Coverage: `tests/unit/test_input_fallback.py`; validated against the real Acme
  Update-Account-Status dialog markup. Engine `0.0.6a16` → `0.0.6a17`; npm
  unchanged.

## @bubblegum-ai/node 0.0.6-alpha.5 — preflight() script validation

- New `bg.preflight(steps[])`: dry-runs each step against the current page and
  returns `{ instruction, ok, status, confidence, resolver, ref, error }[]`
  **without executing anything** — so you can validate a page's steps in one
  batch (`console.table(report)`) instead of discovering failures one run at a
  time. Steps may be strings or `{ instruction, options }`. Nothing executes, so
  call it once per screen with that screen's steps. Engine unchanged
  (`0.0.6a16`); client `0.0.6-alpha.4` → `0.0.6-alpha.5`.

## 0.0.6a16 — fix(web): DOM clickable fallback for ambiguous clicks

- When a click can't be ground to a unique element from the a11y snapshot
  (e.g. Ant renders two equal `role=button` candidates for one labelled button),
  `act` now falls back to a DOM resolver that finds the single interactive
  element by accessible name + role (the quoted text in the step, else the
  target phrase), collapsing nested matches to the outermost interactive
  ancestor. Same proven pattern as the select / link / table-cell fallbacks —
  so `Click the "Update account status" button` resolves across apps instead of
  raising AmbiguousTargetError.
- Coverage: `tests/unit/test_clickable_fallback.py`; logic validated against the
  real Acme button markup. Engine `0.0.6a15` → `0.0.6a16`; npm unchanged.

## 0.0.6a15 — fix(grounding): role-aware tie-break for clicks (button vs text twin)

- A click on a labelled control that wraps a same-text node (e.g. `<button><span>
  Update account status</span></button>`) no longer raises a 0.00-gap
  AmbiguousTargetError. When two candidates tie on confidence, the engine now
  prefers the one whose role best fits the action (button/link/option… over a
  non-interactive text twin) and only reports ambiguity when they're genuinely
  equivalent. Duplicates of the same *specific* ref are collapsed; distinct
  generic role-only refs (e.g. several nameless comboboxes) stay distinct, so
  real ambiguity is still surfaced.
- Coverage: `tests/unit/test_ambiguity_role_tiebreak.py`. Engine `0.0.6a14` →
  `0.0.6a15`; npm client unchanged (`0.0.6-alpha.4`).

## 0.0.6a14 — fix(web): verify checks quoted text inside a descriptive phrase

- `verify` now treats **quoted text as the literal thing to assert**, so a
  natural description works: `verify('the page is shown with an "Update account
  status" button')` checks for `Update account status`, and
  `verify('account status is "Active"')` checks for `Active` — instead of
  failing because the whole sentence isn't literally on the page. Multiple
  quoted phrases must all be visible (`verify('shows "Active" and "Verified"')`).
  Unquoted verifies and an explicit `expected_value` are unchanged.
- Coverage: `tests/unit/test_verify_quoted_text.py`. Engine `0.0.6a13` →
  `0.0.6a14`; npm client unchanged (`0.0.6-alpha.4`).

## 0.0.6a13 — feat(web): click by table cell (column + row) and by link text

- Two new ways to click an element addressed by **what it is**, not its (often
  dynamic) text — e.g. a table link whose label is a UUID:
  - **By table coordinates:** "under the RecordID column, click the 1st row value",
    "Click the RecordID link in the first result row", "click the last row Name",
    or 'in the row where Name is "X", click the RecordID value'. Structured form:
    `act("…", column="RecordID", row="first")` / `row=-1` / `row_match={"Name": x}`.
    Locates the table (Ant `.ant-table`, native `<table>`, ARIA grid), the column
    by header, the row by index (1-based, -1 = last) or by another column's value,
    and clicks the cell's link/button (or the cell).
  - **By link text:** "click the link with text \"<id>\"" or `act("…",
    link_text=id)` — exact → case-insensitive → substring; great for DB-sourced
    ids.
- Node client: `bg.clickInTable({ column, row?|rowMatch?, timeoutMs? })` and
  `bg.clickLink(text, { exact?, timeoutMs? })`.
- Coverage: `tests/unit/test_table_action.py`, Node forwarding tests, and
  `tests/integration/test_table_action_web.py` against the `ant_table` page
  (RecordID cells now contain dynamic-id links). Validated against the real Acme
  table markup. Engine `0.0.6a12` → `0.0.6a13`; `@bubblegum-ai/node`
  `0.0.6-alpha.3` → `0.0.6-alpha.4`.

## 0.0.6a12 — fix(web): DOM fallback disambiguates multiple nameless selects

- "Select X from the Y dropdown" now works on pages with **several nameless
  comboboxes** (the case a11 still failed: best 0.57, "15 candidates"). When the
  a11y snapshot can't ground a unique combobox, the SDK falls back to a
  DOM-based resolver that scores every visible select/combobox by its associated
  **label** (strongest), **placeholder**, **currently-displayed value**, and
  text against the step's target phrase and value, then drives the best match.
  This picks the right control whether it's identified by a form label
  ("Participant status", "Reason") or by the value it shows ("search type" →
  the select showing "Participant"). Works across Ant Design / MUI / CDK /
  native `<select>`.
- Coverage: `tests/unit/test_select_trigger_fallback.py` and a new `multi_select`
  widget-lab page + `tests/integration/test_multi_select_web.py`. The scoring was
  validated against the real captured Acme markup.
- Engine `0.0.6a11` → `0.0.6a12`; npm client unchanged (`0.0.6-alpha.3`).

## 0.0.6a11 — fix(grounding): reliably resolve nameless/value-named selects

- A "select X from the Y dropdown" step could flake between resolving (~0.72)
  and failing with `LowConfidence` (~0.57) depending on whether the page exposed
  the combobox as nameless or with its value as the accessible name. The
  grounding engine now, **only for dropdown/select intents**, accepts the best
  `combobox`/`listbox` candidate above the reject threshold (0.50) instead of
  requiring the 0.70 review bar — a custom select legitimately tops out at
  role-fit confidence. It fires for a uniquely-identifiable combobox (named, or
  the single combobox on the page); multiple indistinguishable nameless
  comboboxes still fail safely rather than guessing.
- Clearer `LowConfidenceError` message (no longer hard-codes "reject threshold
  0.50").
- No behaviour change for non-dropdown steps. Coverage:
  `tests/unit/test_dropdown_select_relax.py`. Engine `0.0.6a10` → `0.0.6a11`;
  npm client unchanged (`0.0.6-alpha.3`).

## 0.0.6a10 — feat(web): table assertions (columns + cell values by row)

- New page-scoped **table verification**. `verify` can now assert a data table's
  columns and cell values instead of only checking that text exists somewhere on
  the page — the real automation need ("does column X exist?", "is the value for
  this row, under that column, what the DB says?").
  - **Structured (deterministic):**
    `verify("…", assertion_type="table", columns=[…])` and
    `verify("…", assertion_type="table", row_match={col: val}, cell={col: val})`.
  - **Natural language (AI-style):**
    `verify("the table has columns RecordID, Account Status and Profile Status")`,
    `verify('in the row where Name is "X", Account Status is "Active"')`,
    `verify('the Account Status column shows "Active"')`.
  - Reads native `<table>`, **Ant Design `.ant-table`** (header/body split across
    two inner tables — the exact Acme structure), and ARIA `role=table/grid`.
    Matching is whitespace-normalised, case-insensitive, and tolerates a value
    rendered inside a badge (e.g. a "✓ Active" pill). The assertion polls until
    it holds or the timeout elapses, so it waits out async-loaded rows.
  - Node client: new typed `bg.verifyTable({ columns?, row?, cell?, timeoutMs? })`.
- Coverage: `tests/unit/test_table_assertions.py` (NL parsing, matcher eval,
  verify routing), `tests/integration/test_table_assertions_web.py` against a new
  `ant_table` widget-lab page, and a Node `verifyTable` forwarding test.
- Engine `0.0.6a9` → `0.0.6a10`; `@bubblegum-ai/node` `0.0.6-alpha.2` →
  `0.0.6-alpha.3`.

## 0.0.6a9 — fix(web): match Ant Design option rows directly by class + title/text

- 0.0.6a8 resolved role-less options via the trigger's `aria-controls` listbox,
  but Ant Design's `rc-select` points `aria-controls` at a *separate, off-screen*
  a11y listbox — the **visible**, clickable rows live in the `.ant-select-dropdown`
  popup as `<div class="ant-select-item-option" title="V">` (label in a
  `.ant-select-item-option-content` child). So the option still wasn't found.
  `_do_select` now also matches the visible option **directly** by
  `.ant-select-item-option[title="…"]` / by option-class text, plus a generic
  open-popup (`role=listbox`/`menu`/`.ant-select-dropdown`) text/title match.
  Verified the selector resolves uniquely against the real captured DOM (and
  does not hit the trigger's `.ant-select-selection-item` label).
- Resolution now waits once for the popup to render, then uses `count()` to skip
  non-matching shapes instantly (no per-attempt timeout burn).
- The `ant_select` widget-lab page now mirrors the real structure (portal
  `.ant-select-dropdown` with role-less rows + a separate off-screen
  `aria-controls` listbox). Engine `0.0.6a8` → `0.0.6a9`; npm unchanged.

## 0.0.6a8 — fix(web): resolve role-less combobox options via the owned listbox

- Ant Design's `rc-select` renders option rows as **role-less**
  `<div class="ant-select-item-option" title="…">` inside a virtualized list, so
  the `get_by_role("option")` lookup added in 0.0.6a7 found nothing and `select`
  failed with "could not find a dropdown option …". `_do_select` now falls
  through to the listbox the trigger **owns** (`aria-controls` / `aria-owns`) and
  matches the option by **text, then title** *within that container* — standard
  ARIA, and scoping to the popup keeps the match off the trigger's own selection
  label (which carries the same value text). Standard `role=option`/`menuitem`
  widgets are still matched first.
- The `ant_select` widget-lab page is now role-less to mirror real rc-select;
  unit coverage adds the owned-listbox text and title fallbacks.
- Engine `0.0.6a7` → `0.0.6a8` (PyPI). npm client unchanged (`0.0.6-alpha.2`).

## 0.0.6a7 — fix(web): force-open Ant Design-style comboboxes (overlay interception)

- The custom-combobox `select` (0.0.6a6) opened the trigger with a normal click,
  which Ant Design (and similar widgets) break: the inner `role="combobox"`
  `<input>` is covered by a `.ant-select-selection-item` `<span>` that intercepts
  the click (Playwright: "`<span>` intercepts pointer events"), so opening timed
  out. `PlaywrightAdapter._do_select` now **force-clicks the trigger open when a
  normal click is intercepted** (a short normal-click probe runs first, so
  plain-clickable `<button>`/`<div>` comboboxes keep their full actionability
  checks).
- New `ant_select` widget-lab page reproduces the overlay structure (inner
  `role=combobox` input under a selection span, current value also an option).
  Coverage: unit `test_custom_combobox_force_opens_when_overlay_intercepts` and
  the `--playwright` integration `test_one_step_select_from_ant_style_overlay_combobox`.
- Engine `0.0.6a6` → `0.0.6a7` (PyPI). npm client unchanged (`0.0.6-alpha.2`).

## 0.0.6a6 — feat(web): one-step selection from custom (non-native) comboboxes

- Engine `0.0.6a5` → `0.0.6a6` (PyPI `bubblegum-ai`). Upgrade with
  `pip install -U "bubblegum-ai==0.0.6a6"`.
- `@bubblegum-ai/node` `0.0.6-alpha.1` → `0.0.6-alpha.2` (npm): **version-parity
  bump only — no client code change.** The feature is entirely engine-side; the
  existing client already forwards the natural-language step. The `alpha.1`
  client also works against engine `0.0.6a6`.

- **`select` now drives div/button-based comboboxes**, not just native
  `<select>`. Ant Design / MUI / Angular CDK / React-Select render
  `role="combobox"` triggers whose options live in a portal listbox;
  `locator.select_option()` can't drive these. `PlaywrightAdapter._do_select`
  now detects the trigger is not a `<select>` (by tag name — both surface as
  `role=combobox` in the a11y tree) and instead **opens the trigger, then clicks
  the matching `role="option"`/`role="menuitem"`**. The native `<select>` path
  is unchanged.
- This lets testers select from custom dropdowns with a single plain-English
  line and **no DOM selectors** — e.g. `Select "Participant" from the search
  type dropdown`. Searching options by accessible name also resolves the common
  ambiguity where the trigger displays the selected value and an option carries
  the same text (the option is targeted explicitly). The existing two-step flow
  (`Open the X dropdown` + `Click <option>`) keeps working.
- Coverage: `tests/unit/test_custom_combobox_select.py` (dispatch: native vs.
  custom, exact→non-exact option fallback, clear error on no match) and
  `tests/integration/test_custom_combobox_select_web.py` (live `--playwright`
  flow against the `combobox` / `nameless_combobox` / `select` widget-lab pages).

## 0.0.6a5 — fix: report.write over the bridge

- Fixed `report.write` (Node-client reporting) crashing with
  `TypeError: 'method' object is not iterable`. `BubblegumSession.results` is a
  **method**, but the bridge handler used it as a property and passed the bound
  method to the reporters. Now normalized (calls it when callable). The unit-test
  fake modelled `results` as a property, which hid the bug — it now mirrors the
  real method shape so the regression is covered.
- Engine `0.0.6a4` → `0.0.6a5`. Node client unchanged (`bg.report(...)` is fixed
  purely engine-side; upgrade with `pip install -U "bubblegum-ai==0.0.6a5"`).

## Release: engine 0.0.6a4 + @bubblegum-ai/node 0.0.6-alpha.1

- Engine `0.0.6a3` → `0.0.6a4` (PyPI): ships the `report.write` bridge
  capability, dynamic-value tokens, and trailing-context stripping.
- Client `@bubblegum-ai/node` `0.0.6-alpha.0` → `0.0.6-alpha.1` (npm): ships
  `bg.report(...)` and the dual ESM/CommonJS build.
- Release order matters: publish the **engine first** (the client's `report()`
  capability-checks for `report.write` and throws against an older engine).

## Node client: reports + dual ESM/CommonJS build

- **Reports from the Node client.** New `report.write` bridge method (capability
  `report.write`) writes Allure / HTML / JSON / JUnit from the session's
  accumulated `StepResult`s, reusing the same writers as the pytest plugin — so a
  Node-driven run gets identical reports without pytest. Exposed as
  `bg.report({ html, allure, junit, json, title, suiteName })` →
  `{ written, steps }`; each format optional (`true` = default name). Engine
  coverage in `tests/unit/test_bridge.py`; client coverage in
  `clients/node/test/client.test.mjs`.
- **Dual ESM + CommonJS build** for `@bubblegum-ai/node`. `tsc` now emits ESM to
  `dist/esm` and CommonJS to `dist/cjs` (with per-dir `package.json` `type`
  markers); the package `exports` map routes `import` and `require` accordingly.
  Consumers on CommonJS runners (e.g. Jest's default runtime) can `require(...)`
  without the `.mts` rename or loader flags; ESM `import` is unchanged. CJS load
  smoke-tested in `clients/node/test/cjs-require.test.cjs`.

## Parameterised values + target-isolation polish + one-click PyPI

- **Dynamic-value tokens** (parameterised dates/times). Any step value may now
  contain a `{{ ... }}` token that expands at run time, so a date picker can be
  fed a *relative* date instead of a literal that goes stale:
  `act('Enter "{{today+7d|%d/%m/%Y}}" into Start date')`,
  `act('Enter "{{now+2h|%d/%m/%Y %H:%M}}" into Appointment')`. Bases `today` /
  `now` / `tomorrow` / `yesterday`; chainable signed offsets `+7d -3d +2w +1mo
  -1y +2h +30min +45s`; optional `|strftime` format (defaults `%Y-%m-%d` and
  `%Y-%m-%d %H:%M`). Token-free and unrecognised values pass through untouched.
  Substitution runs in `_decompose_for` so it covers every channel and both the
  Python SDK and the Node client over the bridge. New module
  `bubblegum/core/parser/dynamic_value.py`; coverage in
  `tests/unit/test_dynamic_value_tokens.py`.
- **Trailing positional-context stripping.** Target isolation now drops a
  trailing "where on the page" tail so it stops diluting text matching:
  `Click the Save button on the Challenges page` → `Save`, `Click the Customer
  Care menu in the top navigation bar` → `Customer Care menu`. Deliberately
  narrow — requires a preposition + article + page-region noun (`page`,
  `screen`, `header`, `footer`, `nav(igation) bar`, `toolbar`, `sidebar`,
  `banner`, …), so bare region names and meaningful relational scopes
  (`in the confirmation modal`, `from the country dropdown`) are untouched.
  Coverage in `tests/unit/test_trailing_context_strip.py`.
- **One-click PyPI publish.** `publish.yml` now takes a `publish` boolean on
  `workflow_dispatch` (mirroring `npm-publish.yml`): unchecked = dry-run to
  TestPyPI, checked = real release to PyPI from the Actions UI — no tag, no
  stale-commit risk. The existing `v*` tag-push path is unchanged.

## 0.0.6a3 — hover role-fit (no more button-vs-span ambiguity)

- The `hover` action now shares the interactive-role preference of `click`/`tap`
  in `role_fit_score`, so hovering an antd `ant-dropdown-trigger` `<button>`
  cleanly outranks its inner text `<span>` instead of tying into an
  `AmbiguousTargetError` (top-2 within the 0.05 gap). Coverage added in
  `tests/unit/test_hover_action.py`.
- Version bump `0.0.6a2` → `0.0.6a3`.

## Engine 0.0.6a2 — CDP attach + hover on PyPI

- Bumped `0.0.6a1` → `0.0.6a2` so the first published build containing **both**
  CDP attach and the new `hover` action gets a distinct version — a clean
  `pip install -U bubblegum-ai` (avoids colliding with the interim `0.0.6a1`
  installed straight from git).

## Web: native `hover` action (reveal hover-triggered menus)

- Added a first-class `hover` web action so hover-revealed dropdowns/menus no
  longer need a raw-Playwright fallback. `act("Hover over the Create menu")` (or
  `act('Hover "+ Create a challenge"', { action_type: "hover" })`) resolves the
  element and dispatches `locator.hover()`.
- Parser maps the `hover` verb (and the natural "hover over X" phrasing) to
  `action_type="hover"`; added to the `ActionPlan` schema and the web adapter
  dispatch table. Click/tap/etc. target extraction is unchanged.
- Coverage: `tests/unit/test_hover_action.py`. Mobile/other channels unchanged.

## Engine 0.0.6a1 — ship CDP attach to PyPI

- Bumped the engine `0.0.6a0` → `0.0.6a1`. The PyPI `0.0.6a0` build predated the
  CDP-attach feature (`channel.web.cdp`, PR #226), so `@bubblegum-ai/node`'s
  `attach()` correctly refused against it (`BridgeError -32003 ... upgrade
  bubblegum-ai`). `0.0.6a1` is the first PyPI engine that advertises
  `channel.web.cdp`, realigning the published engine with the npm client.
- No code changes beyond the version bump — CDP support already merged on `main`.

## npm: one-click publish + Node client demo examples

- `npm-publish.yml` now supports a **one-click "publish for real"**: a manual
  `workflow_dispatch` run with the `publish` box checked publishes from `main`
  (no tag, no stale-commit risk); unchecked stays a dry run. Tag-push
  (`node-v*`) publishing is unchanged. `docs/publishing.md` documents both paths.
- Added `clients/node/examples/` — copy-paste demos: `demo-engine-owned.mjs`
  (quickest try; the engine launches its own browser) and `login.spec.ts`
  (`@playwright/test` + CDP attach, driving the test's own browser), plus a
  README with prerequisites and troubleshooting. Examples are repo-only (not
  shipped in the npm tarball).

## Docs + CI: TypeScript/JS how-to guide and npm publish workflow

- Added `docs/HOW_TO_USE_TYPESCRIPT.md` — a tester-facing copy-paste guide for
  driving Bubblegum from JS/TS via `@bubblegum-ai/node`: prerequisites (Python
  engine + Node), install, the four primitives, `StepResult`, per-call options,
  CDP attach (client-owned browser), a `@playwright/test` fixture pattern,
  mobile, error handling, versioning, and troubleshooting. Linked from the README
  and the Web how-to guide.
- Added `.github/workflows/npm-publish.yml` — publishes `@bubblegum-ai/node` to
  npm: manual dispatch does `npm publish --dry-run`; a pushed `node-v*` tag does a
  real `npm publish --provenance`. Uses a separate `node-v*` tag namespace so it
  never collides with the Python `v*` releases, and a normal merge never
  publishes. `docs/publishing.md` documents the one-time npm org/scope + token
  setup and the release runbook.

## Client-owned browser: CDP attach (0.3.0 slice)

- The bridge can now attach the engine to a **caller-owned Chromium over CDP**
  instead of launching its own, so a TS/JS Playwright test and the engine share
  one browser. `session.open` gains `cdp_endpoint` (e.g. `http://localhost:9222`)
  and `page_index`; the engine connects via `connect_over_cdp`, resolves against
  an existing page, and on close only **disconnects** — it never creates or
  closes the caller's browser/page.
- Advertised as a new capability `channel.web.cdp` (additive — `PROTOCOL_VERSION`
  stays `1`; older clients are unaffected). `select_cdp_page` flattens pages
  across contexts and raises clear errors for an empty endpoint / out-of-range
  index. Coverage: `tests/unit/test_bridge_cdp.py` (fake browser, no real CDP).
- `@bubblegum-ai/node`: new `Bubblegum.attach({ cdpEndpoint, pageIndex? })` (and
  `cdpEndpoint`/`pageIndex` on `launch`) that feature-detects `channel.web.cdp`
  and throws a clear error against an engine too old to support it. Client tests
  cover the present/absent-capability paths.
- Docs: `docs/bridge-protocol.md` (cdp params + capability) and the client README
  (CDP attach example) updated.

## npm client scaffold: @bubblegum-ai/node (0.2.0 slice)

- Added `clients/node/` — a Node/TypeScript client (`@bubblegum-ai/node`) that
  drives the engine from JS/TS by spawning `python -m bubblegum.bridge` and
  speaking its JSON-RPC protocol. No grounding logic is re-implemented in TS; the
  Python engine stays the single source of truth (per
  `docs/distribution-npm-and-pypi.md`).
- `Bubblegum.launch()` spawns the bridge, negotiates via `handshake` (refuses an
  unsupported `protocol_version`), and opens an engine-owned session; `act` /
  `verify` / `extract` / `recover` / state probes / `explain` / `summary` /
  `close` proxy 1:1 to the bridge and return the same `StepResult` shape as the
  Python SDK. Typed mirrors of the protocol + schemas live in `src/protocol.ts`
  and `src/types.ts`.
- Lower-level `BridgeClient` with an injectable `Transport` (default spawns the
  Python process); 8 browser/Python-free tests drive the full client/session over
  a mock transport (`test/client.test.mjs`). Verified end-to-end against the real
  bridge (handshake) too.
- Added `.github/workflows/node-client.yml` (type-check + build + test, scoped to
  `clients/node/**`). Client README documents prerequisites, the API, versioning,
  and the not-yet-built client-owned (CDP-attach) browser model.

## Post-release: v0.0.6-alpha published + publish-workflow hardening

- `bubblegum-ai 0.0.6a0` is **published to PyPI** (first PyPI release), via the
  tag-push (`v0.0.6-alpha`) run of the Trusted-Publishing workflow.
- Hardened `.github/workflows/publish.yml` with `skip-existing: true` on both the
  TestPyPI and PyPI publish steps, so re-running a build for an already-uploaded
  version is a no-op success instead of a hard `400 File already exists` (which is
  what a repeat manual TestPyPI dry run hit — harmless, but noisy/red).
- Flipped the README "latest release" badge `v0.0.5-alpha` → `v0.0.6-alpha`.
- Synced `RELEASE_CHECKLIST.md` to `0.0.6a0` / `v0.0.6-alpha` and updated the
  "publishing deferred" notes — PyPI publishing is now enabled (see
  `docs/publishing.md`).

## CI: PyPI publish workflow (Trusted Publishing / OIDC)

- Added `.github/workflows/publish.yml` — publishes the built distribution via
  **PyPI Trusted Publishing** (OIDC), so no API tokens are stored as repo
  secrets. A `build` job runs the strict release gates (`validate_package.py`
  default + `--strict`, metadata tests, `python -m build`, `twine check`); a
  manual run uploads to **TestPyPI** (dry run) and a pushed `v*` tag uploads to
  **PyPI**. A normal merge never publishes — only a tag push does.
- Added `docs/publishing.md` — the one-time maintainer setup (exact pending
  trusted-publisher values for TestPyPI/PyPI + the `testpypi`/`pypi`
  environments) and the dry-run → tag-release → verify runbook.

## Release prep: bump to 0.0.6a0 + correct repository URLs

- Bumped the package version `0.0.5a0` → `0.0.6a0` (`pyproject.toml`,
  `bubblegum.__version__`, and the `test_package_metadata` assertion) to open the
  `v0.0.6-alpha` pre-release line — the first version targeting PyPI publish and
  the npm client per `docs/distribution-npm-and-pypi.md`.
- Corrected the repository URLs from the placeholder `bubblegum-ai/bubblegum`
  org to the actual `bishnu133/bubblegum` repo, in the `pyproject.toml`
  `[project.urls]` metadata (Homepage/Repository/Issues) and the README badges,
  so published package metadata links resolve.
- The README "latest release" badge still points at `v0.0.5-alpha` — it is
  updated when the `v0.0.6-alpha` GitHub release is actually cut.

## Bridge: drive the engine over JSON-RPC (npm/non-Python clients)

- Added `bubblegum.bridge` — a **JSON-RPC 2.0** server that exposes the engine to
  non-Python clients (the foundation for the planned `@bubblegum-ai/node` npm
  package; see `docs/distribution-npm-and-pypi.md`). Newline-delimited, one
  request per line, served over stdio via the new `bubblegum bridge` command
  (and `python -m bubblegum.bridge`).
- Methods mirror the SDK 1:1: `handshake` (version/capability negotiation),
  `session.open`/`session.close` (engine-owned Playwright/Appium sessions keyed
  by id), `act`/`verify`/`extract`/`recover`, `explain`, the state probes
  (`is_visible`/`is_checked`/`selected_value`), `summary`, and
  `configure_runtime`. Primitive results are the existing `StepResult`
  serialized as JSON, so the wire shape matches the Python SDK exactly.
- `PROTOCOL_VERSION = 1`, advertised with a capability list, so future
  enhancements ship **additively** (newer engine keeps serving older clients).
- Handlers are a thin adapter over `BubblegumSession`/`bubblegum.core.sdk` — no
  grounding logic is duplicated. Session construction goes through an injectable
  factory, so the protocol/dispatch/handlers are unit-tested with no browser or
  device (`tests/unit/test_bridge.py`, 14 tests). Reference: `docs/bridge-protocol.md`.
- Additive only: no changes to existing SDK/schema/public API.

## Documentation: split how-to guides + npm/PyPI distribution strategy

- Added `docs/HOW_TO_USE_WEB.md` and `docs/HOW_TO_USE_MOBILE.md` — two focused,
  self-contained, copy-paste how-to guides (split out of the combined
  `USER_GUIDE.md`) so web (Playwright) and mobile (Appium) adopters each get a
  channel-specific reference: install, the four primitives, `BubblegumSession`,
  the NL grammar, every action type, verify/extract, channel-specific features
  (web: iframes/nav-wait/a11y/network asserts; mobile: system dialogs, WebView
  switching, network conditions, device cloud), self-healing, pytest, and the
  full config reference.
- Added `docs/distribution-npm-and-pypi.md` — design/strategy for shipping
  Bubblegum on **both PyPI and npm**. Recommends a single Python engine exposed
  over a thin JSON-RPC **bridge** with a typed Node/TypeScript client
  (`@bubblegum-ai/node`), rather than a second TS engine. Covers the bridge
  module + `bubblegum bridge` CLI, engine-owned vs client-owned (CDP attach)
  browser models, a SemVer + `PROTOCOL_VERSION` (additive-first, capability-
  negotiated) versioning scheme so newer engines keep serving older clients, a
  forward-looking release ladder to a `1.0.0` stable contract, and dual-publish
  CI mechanics. Design-only — no engine code changes.
- README now links the two how-to guides and the distribution strategy.

## Documentation: end-to-end user guide

- Added `docs/USER_GUIDE.md` — a single, example-driven reference covering every
  Bubblegum capability with **separate Web and Mobile sections**: the four
  primitives, `BubblegumSession`, the natural-language grammar, all action types,
  iframes, nav-wait, select-by-label, state probes, dialogs/scopes, re-grounding,
  `recover()`, self-healing, memory cache, vision/OCR, BDD, the pytest plugin,
  and the full config reference. Intended as the copy-paste starting point for
  teams adopting Bubblegum in their automation.

## Web reliability: iframes, bounded nav-wait, select-by-label, strict-mode + re-grounding

Five web-channel improvements to the Playwright adapter and SDK resolution loop:

- **iframe support.** `collect_context()` now merges child-frame accessibility
  snapshots, so elements inside same-origin `<iframe>`s are discoverable by the
  resolvers. Execution and text extraction route into the owning frame
  (`_resolve_action_locator`). Gated by `ContextRequest.include_frames`
  (default on); a no-op for frameless pages.
- **Bounded, configurable post-click navigation wait.** A non-navigating
  (AJAX/SPA) click previously burned a fixed 5 s on the `wait_for_url` probe.
  It is now two-phase — cheaply detect whether a navigation commits within
  `ExecutionOptions.nav_wait_ms` (default 1 s), and only then wait for the new
  document to settle using the full action timeout. Set `nav_wait_ms=0` to skip.
- **`<select>` by visible label.** `select` now tries the option value, then
  falls back to the visible label, so `Select "United States" from Country`
  works even when the option value differs (`value="US"`).
- **Strict-mode retry.** An action whose ref matches more than one DOM node
  retries on `.first` (mirroring the read path) instead of failing the step.
- **Re-grounding for late-rendered elements.** `act()/verify()/extract()`
  re-collect context and retry resolution (`grounding.resolve_retries`,
  default 2 × `resolve_retry_interval_ms` 300 ms) when the first attempt finds
  nothing, so SPA elements that render a beat late resolve instead of failing.

Web text extraction now delegates to `PlaywrightAdapter.extract_text()` (parity
with the mobile channel). New fixtures: `widget_lab/iframe.html` +
`iframe_inner.html`. Coverage: `tests/unit/test_web_resilience.py` (browser-free)
and `tests/integration/test_phase22e10_web_resilience_e2e.py` (live, `--playwright`).

## Self-healing advisory survives memory-cache replays

- A self-healing substitution (e.g. a step written for "login" that resolves to
  "Sign In") was flagged on the first run but went silent on every subsequent
  run, because the step then replayed from the memory cache (`memory_cache`
  resolver) rather than `fuzzy_text`. The advisory is now built **before** the
  resolution is persisted, so it is stored in the cached metadata and
  re-surfaced on replay (tagged `replayed_from_cache`). A replayed healed step
  stays `recovered` instead of being silently downgraded to `passed`.
  Coverage: `tests/unit/test_self_healing_advisory.py`.

## Vision tier validation on deterministic-hard targets

- Added `tests/unit/test_vision_deterministic_hard.py`: proves the AI (vision)
  tier wins grounding on an icon/image control with **no** accessible name (where
  the text/role resolvers cannot match), that it does **not** displace a clean
  deterministic match, and that the same target fails to resolve when vision is
  unavailable or cost-blocked. No API key required (candidates are injected
  exactly as the screenshot→provider pipeline injects them).
- Note: web *execution* of a vision win still relies on the deterministic
  hydrator mapping the candidate to a role/text ref — coordinate (bbox) clicking
  for truly nameless controls remains a future enhancement.

## Mobile re-grounding parity

- The SDK re-grounding loop is channel-agnostic, so the late-render retry now
  benefits mobile too. Coverage: `tests/unit/test_mobile_reground.py` (fake
  Appium adapter; full on-device e2e runs via the env-gated
  `tests/real_env/android|ios` suites).

## BDD step library + nameless-combobox fallback

- Added `bubblegum.bdd`: plain-English Given/When/Then on top of the NL engine
  for manual-QA personas. Core is a framework-agnostic dispatcher
  (`execute_step`); `bubblegum.bdd.steps` ships catch-all pytest-bdd When/Then
  bindings (optional extra `bdd` = `pytest-bdd>=7`). Runnable example under
  `examples/web/bdd/`.
- Nameless-combobox resolver fallback: a `role="combobox"` trigger with no
  accessible name (MUI / Angular CDK overlays) now resolves by role + uniqueness
  when the step signals a dropdown, instead of failing below the review band.

## Packaging: bundle quickstart sample pages (v0.0.5a)

- The `widget_lab` and `sample_app` quickstart pages now ship **inside** the
  package (`bubblegum/testing/pages/`), so `pip install bubblegum-ai` users get
  the fixtures without a repository checkout. `find_pages_dir()` resolves a repo
  checkout first (dev) and falls back to the bundled copies (pip install).
- Added `[tool.setuptools.package-data]` so the HTML pages are included in the
  wheel, and a drift guard (`tests/unit/test_packaged_sample_pages.py`) that
  keeps the bundled copies byte-for-byte in sync with the example sources.

## CI + self-healing + AI-first object recognition

- CI now runs the full unit suite on every PR (`.[test,anthropic]`); fixed the
  17 stale baseline test failures so the gate is meaningful.
- Self-healing is no longer silent: a fuzzy/synonym substitution (e.g. a step
  written for "login" that resolves to "Sign In") marks the step `recovered`,
  attaches a `healing` advisory, and is highlighted in the HTML/JSON reports as
  a possible defect to revisit.
- Added an Anthropic (Claude) vision backend for element grounding from
  screenshots and an opt-in `grounding.ai_first` strategy that runs the AI tier
  before the deterministic tiers (cost-gated, with deterministic fallback).

## Phase 19G-E1 (release checklist baseline sync)

- Phase 19G-E1 docs/checklist-only cleanup: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match the current mainline pytest collection baseline. No runtime/parser/planner/schema/resolver/ranker/confidence/API/dependency/version changes.

## Phase 19F-F (Object Intelligence static summary/reporting MVP)

- Added compact static summary/reporting for Object Intelligence seed fixtures when selected via
  `python scripts/run_benchmarks.py --cases tests/benchmarks/object_intelligence/seed_cases.json`.
- Summary includes deterministic counts for total cases, channel, category, positive vs negative,
  failure modes, baseline expectations, expected graph-signal true counts, relation types, and tags.
- Execution remains intentionally unsupported for object seed fixture shape under `--execute`, with
  clear nonzero operator message unchanged.
- Default regression benchmark behavior remains unchanged when `--cases` is omitted.

## Phase 19F-D (minimal benchmark runner case-path selection)

- Added non-breaking optional benchmark runner case selection via
  `python scripts/run_benchmarks.py --cases <path>`.
- Default behavior remains unchanged: omitting `--cases` still runs regression fixtures from
  `tests/benchmarks/fixtures/cases.json` with existing static/execute behavior.
- Added safe validation-only support for non-regression fixture shapes (including Object
  Intelligence seed fixture format with top-level `{"cases": [...]}`); these can be loaded in
  static mode and report a clear unsupported message in `--execute` mode.
- Added unit coverage for explicit default fixture path parity, object seed opt-in validation path,
  non-supported execute path behavior, and clear invalid-path failure.

## Phase 19F-B (Object Intelligence benchmark seed fixtures MVP)

- Added Object Intelligence seed spec doc at
  `docs/phase-19f-object-intelligence-seed-spec.md`.
- Added separate Object Intelligence seed fixtures at
  `tests/benchmarks/object_intelligence/seed_cases.json`.
- Added dedicated Object Intelligence seed schema at
  `tests/benchmarks/object_intelligence/schema.json`.
- Added unit validation for seed/schema shape and safety checks at
  `tests/unit/test_object_intelligence_seed_schema.py`.
- Scope is docs/fixtures/schema-validation only; no runner runtime logic, scoring,
  resolver priority, or engine behavior changes in this phase.

# Changelog

- Phase 19E-B metadata-only graph diagnostics MVP: added internal `graph_signals` helper to compute compact, deterministic, JSON-safe graph-context diagnostics (`label_for_match`, `same_row_match`, `same_container_match`, `nearby_label_match`, `role_match_with_graph_context`, `unique_in_scope`, `visible_enabled_match`) and emitted these under `metadata["graph_signals"]` in AccessibilityTreeResolver and AppiumHierarchyResolver candidates. No engine/ranker/confidence/threshold changes, no resolver priority/order changes, no SDK/API/schema/dependency/version changes, and no adapter runtime behavior changes.
- Phase 19E-D graph signal reporting/analytics MVP: report surfaces now preserve sanitized `metadata["graph_signals"]` in JSON output, redact unsafe graph diagnostic payload keys, render an optional compact per-step “Graph Signals” section in HTML reports, and add aggregate `graph_signal_summary` analytics (`total_events`, `presence_counts`, `reason_counts`, `field_true_counts`). Reporting-only scope; no scoring/ranker/confidence/engine/resolver/API/schema/dependency/version changes.

All notable changes to this project will be documented in this file.

## Unreleased
- Phase 19G-O object seed diagnostic runner MVP: added opt-in metadata-only script `scripts/run_object_seed_diagnostics.py` that loads object seed cases + synthetic element sidecar, parses relational intent via existing parser helper, builds `NormalizedElement`/`ElementGraph`, runs `build_graph_query_diagnostics(...)`, and emits compact summary counts with optional compact JSON artifact output. Added synthetic sidecar fixture `tests/benchmarks/object_intelligence/synthetic_elements.json` and focused unit coverage in `tests/unit/test_phase19g_object_seed_diagnostics_runner.py`. No action execution, no resolver/ranker/scoring/filtering/runtime targeting changes, no default benchmark behavior changes, no SDK/API/schema/dependency/version changes.
- Phase 19G-L graph query diagnostics reporting/analytics support: JSON reports now preserve sanitized `metadata["graph_query_diagnostics"]` (safe compact keys only), HTML reports render optional escaped "Graph Query Diagnostics" step sections only when present, and reporting analytics include compact `graph_query_summary` aggregates (`total_events`, `status_counts`, `relation_type_counts`, `ambiguity_count`, `reason_counts`, `matched_id_total`) derived from sanitized diagnostics only. Reporting-only scope; no resolver/query/parser/planner/schema/ranker/confidence/engine/API/dependency/version changes.
- Phase 19G-K resolver metadata-only graph query diagnostics integration: AccessibilityTreeResolver and AppiumHierarchyResolver now attach internal `metadata["graph_query_diagnostics"]` when both relational intent and an ElementGraph context (`element_graph` or `graph`) are available. Diagnostics are produced by existing `build_graph_query_diagnostics(...)` and remain metadata-only (no candidate filtering, no scoring/confidence changes, no resolver priority/order changes, no engine/parser/planner/schema/API/dependency/version changes).
- Phase 19G-I metadata-only graph query diagnostics MVP: added internal `build_graph_query_diagnostics(...)` in `bubblegum/core/elements/query.py` to map `relational_intent` into deterministic, compact, JSON-safe graph-query diagnostics (`status`, `relation_type`, `anchor_resolution`, `scope_resolution`, `matched_ids`, `excluded_ids`, `ambiguity`, `reasons`) across `label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, and `mobile_attr_hint`. Diagnostics-only scope: no runtime candidate filtering/selection, no engine/resolver/ranker/confidence changes, no parser/planner/schema/API/dependency/version changes.
- Phase 19G-G graph query planner design/spec added (`docs/phase-19g-graph-query-planner-design.md`): defines deterministic `relational_intent`→ElementGraph diagnostics mapping, fail-closed ambiguity/status model, container-detection heuristics, JSON-safe diagnostics contract, and phased integration path (diagnostics-first; runtime filtering/scoring deferred). Docs-only; no runtime/parser/planner/schema/resolver/ranker/engine/API/dependency/version changes.
- Phase 19G-E1 docs/checklist baseline sync: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match current mainline test collection. Docs/checklist-only change; no runtime/parser/planner/schema/resolver/ranker/API/dependency/version changes.
- Phase 19G-D parser relational metadata MVP: added internal rule-based `parse_relational_intent(...)` helper for safe relational hints (`for <anchor>`, modal scope phrases, dropdown scope phrases, checkbox label phrases) and metadata-only planner propagation into `StepIntent.context["relational_intent"]` when matched. No resolver/engine/ranker/confidence/schema/API/dependency/version changes; no runtime targeting behavior changes.

- Phase 19G-B relational intent contract design/spec added (`docs/phase-19g-relational-intent-design.md`): defines schema-stable `StepIntent.context["relational_intent"]` metadata proposal, initial relation taxonomy (`label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`), conservative parser principles, backward-compat strategy, pre-implementation test gates, and phased follow-on plan. Design-only: no parser/planner/runtime/ranker/schema/API/dependency/version changes.

- Phase 19C Normalized Cross-platform Element Model MVP added internal-only normalized element contracts in `bubblegum/core/elements/normalized.py` (`NormalizedElement`, `NormalizedBounds`) plus deterministic web/mobile normalization helpers and JSON-safe serialization. Added focused unit coverage for defaults, serialization safety, web/mobile mapping, bounds parsing/clamping, and parent/child linkage. No runtime resolver/ranker/adapter behavior changes, no SDK public API changes, no dependency/version changes.

- Phase 19B Object Intelligence Benchmark and Regression Design docs added (`docs/phase-19b-object-intelligence-benchmark.md`), explicitly separating capability benchmarking from regression protection. Defines benchmark taxonomy (web/mobile), baseline comparison strategy (raw Playwright, raw vision/LLM grounding, current Bubblegum pipeline), required metrics/failure taxonomy, ground-truth case format, fixture scale targets, mobile-specific design track (FrameworkDetector/WebView/SystemDialog/IconLibrary/screen signatures), roadmap reorder through 19M, and explicit deferrals (no multilingual claim yet, no full device-cloud matrix, no Selenium adapter in this phase). Docs/design-only scope; no runtime/API/schema/dependency/version changes.

- Phase 15H wait observability metadata/reporting MVP: adapter execute paths now emit safe wait metadata on existing `StepResult.target.metadata` (`wait_used`, `wait_mode`, `wait_outcome`, `wait_adapter`, optional `wait_duration_ms`) only when `wait_for` is configured. JSON/HTML reporting preserves and safely renders wait metadata while redacting unsafe wait diagnostics fields. Observability-only scope; no wait behavior/retry behavior/schema/public-API/dependency/version changes.

- Phase 15F adapter-level explicit wait_for MVP: execute-path adapters now consume existing `ExecutionOptions.wait_for` + `timeout_ms` without schema/API changes. Playwright supports `visible`/`attached`/`enabled` pre-action waits; Appium supports `present`/`visible` pre-action waits with timeout-bounded visibility polling. Defaults remain backward-compatible when `wait_for` is `None`; retry cap/classification/metadata behavior unchanged. Added focused mock-based unit tests for wait modes, unsupported-mode failure clarity, and retry-with-wait behavior.
- Phase 15D retry observability metadata/reporting MVP: adapter execute paths now surface safe retry metadata on existing `StepResult.target.metadata` fields (`retry_attempts`, `retry_transient`, `retry_reason`, `retry_adapter`) for Playwright/Appium execution outcomes. JSON/HTML reporting preserves and safely renders retry metadata while redacting unsafe retry diagnostics fields. Observability-only scope; no retry behavior change, no schema/public-API/dependency/version changes.
- Phase 15B adapter-level transient retry/wait MVP: added conservative execute-only transient retry helpers in Playwright and Appium adapters (retry budget capped to 1, transient-message classification only, no resolver/grounding/provider retries). Added focused unit tests for transient/pass, permanent/fail, and retry-budget behavior. No public API/schema/dependency/version changes.
- Phase 14E docs/examples polish pass: added explicit run commands for key local examples, clarified direct-NL adoption wording around config/cost/provider/privacy-gated fallback behavior, and documented reserved pytest plugin flags (`--bubblegum-ai`, `--bubblegum-memory`). Docs/examples-only scope with no runtime/API/dependency/version changes.
- Phase 14C adoption/examples smoke-kit docs MVP added: `docs/adoption.md`, `docs/pytest-plugin.md`, `docs/ci.md`, plus new examples `examples/web_nl_quickstart.py`, `examples/ocr_callable_hydration_example.py`, and `examples/report_artifacts_example.py`. Updated `README.md`, `examples/README.md`, and `RELEASE_CHECKLIST.md` with adoption links and verification commands. Docs/examples-only scope with no runtime/API/dependency/version changes.

- Phase 19D UI Element Graph MVP added internal `ElementGraph` over `NormalizedElement` (`bubblegum/core/elements/graph.py`) with deterministic parent/child/sibling/nearby/label_for/same_row/same_container relationships and safe query helpers (`get_element`, `children_of`, `parent_of`, `siblings_of`, `nearby`, `labels_for`, `controls_for_label`, `elements_with_text`, `elements_by_role`) plus JSON-safe summary export. Added unit coverage for graph construction, deterministic relations, lookup helpers, unknown-id safety, and serialization safety. No resolver/ranker/adapter runtime integration, no SDK public API changes, no dependency/version changes.

## v0.0.5-alpha
- Release scope finalized for GitHub pre-release `v0.0.5-alpha` with package version `0.0.5a0` (PEP 440).
- Scope includes:
  - Phase 17A roadmap reset and `v0.0.5-alpha` planning
  - Phase 17B real smoke kit/adoption readiness audit
  - Phase 17C real smoke kit docs/examples MVP
  - Phase 17D smoke runner audit
  - Phase 17E dependency-free infra-free smoke runner MVP
  - Phase 17F smoke runner post-merge verification
  - Phase 17G release checklist collect-only baseline sync to 615
  - Phase 18B release metadata/docs/checklist preparation
- No runtime behavior changes.
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/network/browser/device CI smoke added.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.4-alpha
- Release scope finalized for GitHub pre-release `v0.0.4-alpha` with package version `0.0.4a0` (PEP 440).
- Scope includes:
  - Phase 14 adoption docs/examples polish
  - Phase 15B adapter-level transient retry MVP
  - Phase 15D retry observability metadata/reporting
  - Phase 15F adapter-level explicit `wait_for` MVP
  - Phase 15H wait observability metadata/reporting
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/LLM/OCR/vision retry behavior changes.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.3-alpha
- Release scope finalized for GitHub pre-release `v0.0.3-alpha` with package version `0.0.3a0` (PEP 440).
- Phase 13 feature track included: VisualRefHydrator safe boundary/fail-safe behavior, deterministic web hydration (OCR/vision metadata), deterministic mobile hydration (`hierarchy_xml` text/content-desc/resource-id), sanitized SDK hydration diagnostics, JSON/HTML hydration diagnostics reporting, and hydration analytics summary.
- Publish-check hygiene from Phase 13C/13E retained for clean artifact verification (`rm -rf dist build *.egg-info` before `python -m build`).
- No runtime behavior changes, no public API breaking changes, no dependency changes in this release-prep slice.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

- Phase 13Q hydration diagnostics analytics summary MVP: reporting analytics now include `hydration_summary` aggregate categorical counts (`total_events`, status/source/strategy/channel/reason) derived from report-safe hydration metadata only. Excludes refs and raw/sensitive payload-bearing fields. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13O hydration diagnostics reporting MVP: JSON reporting preserves sanitized hydration metadata with report-layer non-leakage guardrails; HTML reporting now renders a compact per-step hydration diagnostics section only when hydration metadata exists. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13M hydration diagnostics visibility MVP: SDK hydration boundary for visual refs now surfaces stable non-sensitive hydration metadata (status/reason/original_ref/hydrated_ref/channel/source/strategy plus match_field and match_count for ambiguous/no-match cases) on StepResult-facing outputs without changing hydration decisions or execution behavior. Sanitization excludes hierarchy XML, screenshots/bytes, base64/raw payloads, secrets, and candidate dumps. No public API/adapter/resolver/provider/dependency/version changes.
- Phase 13K deterministic mobile visual-ref hydration MVP: `VisualRefHydrator` now supports mobile hierarchy XML exact mapping for synthetic visual refs using deterministic metadata and priority fields `text` -> `content-desc` -> `resource-id`, emitting Appium-executable JSON XPath refs on unique matches. Stable fail-safe reasons are used for missing/invalid hierarchy, unsupported metadata, no-match, and ambiguous matches. No bbox/center-tap fallback, no screenshot/provider calls, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13I deterministic web visual-ref hydration MVP: `VisualRefHydrator` now maps supported synthetic refs to executable web refs using deterministic metadata only (OCR `matched_text`/`text` -> `text="..."`; vision `role` + label/text -> `role=...[name="..."]`, fallback text ref). Mobile visual hydration remains deferred fail-safe. No bbox/center-click fallback, no provider/screenshot calls added, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13G visual ref hydration fail-safe MVP: added `VisualRefHydrator` abstraction and synthetic visual ref detection (`ocr://`, `vision://`) at SDK orchestration boundary for `act()` and `extract()`. Synthetic visual refs are never executed directly; hydration currently fails safe with stable `VisualRefHydrationError` when deterministic mapping is unavailable. No adapter/resolver/provider/public-API/dependency/version changes.
- Phase 13E publish-check artifact hygiene update: publish-readiness workflow now removes stale `dist/`, `build/`, and `*.egg-info` artifacts before `python -m build`; release checklist mirrors the same cleanup command to avoid ambiguous mixed-version artifact checks. No runtime/API/dependency/version changes.
- Phase 13C publish-readiness preparation: added manual-only `.github/workflows/publish-check.yml` to run packaging/validation/build/twine/benchmark/targeted-test/collection gates and upload `dist/` artifacts without publishing. Updated release checklist/readiness notes for deferred TestPyPI/PyPI posture and future trusted-publishing recommendation. No runtime/API/adapter/resolver/dependency/version changes.
- Phase 12D v0.0.2-alpha release-notes/checklist cleanup: finalized release wording and checklist gates for GitHub pre-release readiness. Scope remains documentation-only with no runtime/API/adapter/resolver/dependency/version changes.
- v0.0.2-alpha release scope summary finalized: callable OCR backend + OCR privacy gating; vision abstraction (`VisionProvider`) + callable backend (`CallableVisionProvider`); optional/dependency-light `OpenAIVisionProvider`; provider registration lifecycle (`configure_vision_provider` / `clear_vision_provider`); SDK screenshot-to-vision wiring with explicit privacy gates; `max_cost_level="high"` gate for provider-based screenshot vision; sanitized OpenAI diagnostics; API-correct manual OpenAI example; no mandatory OCR/OpenAI dependencies.
- Release/distribution posture reaffirmed: package version remains `0.0.2a0` for GitHub pre-release `v0.0.2-alpha`; PyPI/TestPyPI publishing remains deferred.
- Phase 11Z SDK cost gating for screenshot-to-vision provider invocation: runtime provider calls now require `ExecutionOptions.max_cost_level="high"` in addition to existing vision/privacy/provider/screenshot gates. Low/medium cost levels fail-safe skip screenshot request (when needed only for provider vision) and skip provider invocation; manual `vision_candidates` remain preserved and unblocked. Added SDK wiring/registration unit coverage.
- Phase 11X OpenAI vision diagnostics hardening: `OpenAIVisionProvider` now exposes sanitized failure metadata (`last_diagnostic` and `get_last_diagnostic()`) with stable `provider`/`code`/`stage`/`recoverable`/`message`/`exception_type` fields while preserving fail-safe `[]` behavior. Diagnostics exclude raw screenshot bytes, base64 payloads, request payloads, API keys/secrets, and raw provider response bodies. Added mock-only diagnostics coverage.
- Phase 11V docs/examples adoption hardening: added manual optional real-provider usage example (`examples/openai_vision_provider_manual_example.py`) and linked guidance in README/examples/docs for user-installed OpenAI SDK + `OPENAI_API_KEY`, required vision/privacy gates, and `clear_vision_provider()` teardown. No runtime/API/adapter/resolver/dependency/version changes; network tests/benchmarks remain unchanged.
- Phase 11T OpenAI vision hardening: `OpenAIVisionProvider` now validates explicit `model` (non-empty) and `timeout` (positive), preserves injected-client behavior, propagates timeout during optional lazy SDK client creation, and expands deterministic/mock-only parsing support for `output_text`, plain-string JSON, and simple nested response text shapes. Fail-safe `[]` error handling and screenshot-byte non-persistence policy remain unchanged; no SDK public API/adapter/dependency/version changes.
- Phase 11R optional OpenAI vision backend added (`bubblegum/core/vision/backends/openai.py`) via `OpenAIVisionProvider` implementing the existing VisionProvider contract (`detect_targets(image_bytes, instruction, context=None)`). Supports injected client or optional SDK client creation, encodes image bytes as base64 transport payload, requests structured JSON candidates, normalizes outputs, and fails safe to empty candidates on provider/parse/network errors. Includes mock-only unit coverage; no mandatory OpenAI dependency, no SDK public API/adapter/resolver changes, and no raw screenshot-byte persistence.
- Phase 11P docs/examples adoption slice added: new end-to-end callable vision provider lifecycle example (`examples/vision_callable_provider_example.py`) plus README/docs linkage and recommended setup/teardown (`configure_vision_provider(...)` + `clear_vision_provider()` in `finally`) with required gates (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`). No runtime/API/adapter/dependency/version changes; real OpenAI/Anthropic/Ollama providers remain deferred.
- Phase 11N public vision provider lifecycle API added: exported `configure_vision_provider(provider)` and `clear_vision_provider()` with provider contract validation (`detect_targets(...)`) and idempotent reset semantics. Registration does not invoke provider or bypass privacy/config gates; manual `vision_candidates` precedence, provider fail-safe behavior, and screenshot-byte non-persistence policy remain unchanged.
- Phase 11L callable vision enablement documentation added (`docs/phase-11l-callable-vision-enablements.md`), including callable contract/output examples, required privacy/config gates, manual `vision_candidates` vs optional SDK screenshot wiring guidance, provider non-invocation troubleshooting, raw screenshot persistence prohibition, synthetic `vision://` limitation, and explicit note that real OpenAI/Anthropic/Ollama vision providers remain deferred. Added provider lifecycle/API audit note and Phase 11M recommendation (keep private hook private for now; evaluate safe public registration lifecycle before real provider integrations).
- Phase 11J optional SDK screenshot-to-vision context wiring added: internal runtime plumbing can request screenshots and inject normalized `vision_candidates` only when all gates pass (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, provider configured, screenshot present). Default behavior remains off; manually injected candidates are preserved; no raw screenshot bytes are stored in traces/metadata; no resolver/adapter/public API signature changes.
- Phase 11H vision privacy/config contract hardening: added `privacy.process_screenshots_for_vision` (default `false`) to make screenshot-to-vision processing an explicit opt-in flag. No SDK runtime auto-wiring was added; resolver behavior remains injected-candidate-only and `vision://` refs remain synthetic/non-executable.
- Phase 11F user-supplied vision callable backend added (`bubblegum/core/vision/backends/callable.py`) via `CallableVisionProvider`, enabling runtime-provided vision candidate callables to feed the existing normalized screenshot vision pipeline (still opt-in/privacy-gated, no bundled real vision model dependency).
- Phase 11D VisionModelResolver injected-candidate MVP implemented: resolver now consumes `intent.context["vision_candidates"]`, normalizes via existing vision engine helpers, emits synthetic `vision://target/<index>` candidates with ranker-compatible signals/metadata, and suppresses weak unrelated matches. No real vision provider/model dependency or adapter-executable vision refs added.
- Phase 11B vision abstraction scaffold added (`bubblegum/core/vision/engine.py`): `VisionCandidate`, `VisionProvider` protocol, deterministic `FakeVisionProvider`, candidate normalization, and safe screenshot-to-vision pipeline helper (mock/fake only; no bundled real vision model dependency).

## v0.0.2-alpha
- Phase 10Q release/docs readiness cleanup completed: release checklist collect-only baseline synced to 476, and OCR callable-only contract/privacy gate/synthetic `ocr://` ref limitation documented for v0.0.2-alpha readiness.
- Appium onboarding documentation improvements across README and examples.
- Manual mobile smoke guidance clarified (Appium runtime smoke remains manual and non-CI-gated).
- Release checklist consistency cleanup for reusable pre-release gates.
- OCRResolver injected-block MVP added (context-driven `ocr_blocks`, deterministic synthetic refs `ocr://block/<index>`, no external OCR engine dependency yet).
- Phase 10J planning documentation added for post-OCR MVP verification, risk assessment, and next-slice recommendation (Phase 10K hybrid web + mobile examples).
- Phase 10K hybrid web + mobile examples added (`examples/hybrid_web_mobile_example.py`) with README linkage and guidance (docs/examples only; no runtime behavior changes).
- Phase 10M OCR engine abstraction added (`bubblegum/core/ocr/engine.py`) with deterministic fake engine, OCR block normalization, and mocked screenshot-to-block pipeline helper (no external OCR dependency, no adapter/runtime behavior changes).
- Phase 10O user-supplied OCR callable backend added (`bubblegum/core/ocr/backends/callable.py`) via `CallableOCREngine`, enabling runtime-provided OCR functions to feed the existing normalized screenshot OCR pipeline (still opt-in, no bundled real OCR dependency).
- PyPI/TestPyPI publishing remains deferred; release target continues to be GitHub pre-release tagging for `v0.0.2-alpha`.

## v0.0.1-alpha (MVP RC)

### Highlights
- Playwright explicit-selector quickstart path is in place for deterministic first-run smoke usage.
- Playwright natural-language `act`, `verify`, and `extract` usage paths are available for MVP workflows.
- Mobile channel routing supports `act`, `verify`, and `extract` via Appium adapter wiring.
- Appium quickstart is provided as a real-infrastructure template (server/device/app/capability aligned environment).
- Deterministic benchmark baselines are passing:
  - Static validation: 12/12
  - Execute validation: 12/12

### Known limitations
- Appium quickstart requires real mobile infrastructure:
  - running Appium server
  - running emulator/device
  - installed target app
  - local capability alignment
- Playwright quickstart is deterministic local smoke (`page.set_content(...)`) and is not full real-app coverage.
- Tier 3 AI/LLM/vision/ocr behavior remains optional and depends on explicit configuration, provider setup, and environment.
- PyPI/TestPyPI publishing is deferred for this MVP RC; release target is GitHub pre-release tagging.
