# Phase 19M-K — Real Environment Validation Plan (Plan-Only)

## 1) Purpose

Local unit and fixture tests are necessary but not sufficient for mobile and hybrid automation readiness. They validate deterministic logic (resolver behavior, detector classification, metadata sanitization, and guardrail decisions) under controlled inputs, but they do not exercise real runtime variance such as device timing jitter, simulator/emulator rendering differences, cloud farm capability drift, permission-dialog behavior, keyboard overlays, or WebView lifecycle instability.

This plan defines how Bubblegum object identification and mobile intelligence should be validated progressively across:
- local desktop browsers,
- Android emulator,
- iOS simulator,
- physical Android/iOS devices,
- cloud device/browser providers,
- native and hybrid/WebView surfaces,
- system dialogs,
- scroll/repeated-list/icon-only/relational scenarios.

The objective is to establish measurable confidence before any runtime WebView context switching implementation.

## 2) Current confidence level (local-only baseline)

Current confidence is **strong for metadata and dry-run logic in local test conditions**:
- `context_inventory` metadata capture and sanitization in Appium context collection pipeline.
- `framework_detection` surface classification (`android_native`, `ios_native`, `webview`, `hybrid`, `system_dialog`, `unknown`) with safe evidence/warnings.
- `webview_switch_diagnostics` dry-run recommendation/status model (`switch_attempted=False`).
- `webview_switch_guardrails` policy gating for allow/block/defer/unsupported decisions, opt-in enforcement, and safe diagnostics.
- JSON/HTML reporting path for safe mobile diagnostics fields and redaction expectations.
- benchmark seed expansion coverage (34 object-intelligence seed cases) including mobile/hybrid-relevant patterns.
- **No runtime context switching is implemented** (no `driver.switch_to.context` execution path).

Net: local confidence supports planning and controlled pre-switch hardening, but does not yet validate real-environment behavior.

## 3) Validation goals

Define “ready for real-world alpha usage” as:
1. Bubblegum can resolve and act on representative targets in native + hybrid conditions across emulator/simulator and at least one real device per platform with reproducible pass rates.
2. WebView-related metadata (inventory, detection, diagnostics, guardrails) remains stable, sanitized, and actionable in real sessions.
3. Known fragile scenarios (permissions, keyboard overlays, off-screen elements, repeated rows/cards, weak icon labels) show deterministic fallback behavior and acceptable flake rate.
4. Report outputs remain safe metadata only under real execution logs/artifacts.
5. Cloud execution reproduces local smoke outcomes with bounded divergence and debuggable artifacts.

## 4) Environment matrix

| environment | purpose | required setup | test app type | scenarios | pass criteria | risk covered |
|---|---|---|---|---|---|---|
| Web local | Baseline browser parity and resolver/report sanity | Python env, local browser drivers, static test page | Web page | duplicate labels, modal, form-by-label, same-row action, mobile emulation | >=95% smoke pass, report fields present/safe | browser engine differences, selector ambiguity |
| Android emulator | First mobile runtime validation at low cost | Appium server + UiAutomator2 + Android emulator image | native + hybrid Android sample apps | content-desc, resource-id, permission dialog, scroll/repeated list, WebView metadata | all smoke groups pass; diagnostics emitted; no unsafe leakage | Android timing, emu rendering, WebView exposure |
| iOS simulator | iOS runtime parity without provisioning/device constraints | Xcode simulator + Appium XCUITest | native + hybrid iOS sample apps | label/name/value, XCUIElementType, permission dialog, WebView metadata | all iOS smoke groups pass; diagnostics stable | iOS attribute model differences |
| Android real device | Validate hardware timing/input/runtime variance | USB debugging, adb, Appium, compatible WebView/Chrome | native + hybrid Android sample apps | keyboard behavior, permission dialog, screen-size variance, hybrid context availability | >=90% smoke pass across repeated runs; bounded flake | real device jitter, OEM differences |
| iOS real device | Validate signing/WDA + hardware behavior | provisioning profile, signing, WebDriverAgent, trusted device | native + hybrid iOS sample apps | keyboard behavior, permission prompts, hybrid/WebView behavior | >=90% smoke pass; WDA stability threshold met | signing/WDA instability, physical iOS differences |
| Cloud Android | Cross-vendor/device coverage at scale | provider capabilities, secure secrets, uploaded app builds | native + hybrid Android smoke apps | core native + hybrid smoke, logs/artifacts capture | smoke parity with local within agreed delta | cloud capability drift, network latency |
| Cloud iOS | Cross-vendor iOS matrix and WDA-at-scale check | provider caps, signing-compatible app build, secure secrets | native + hybrid iOS smoke apps | iOS native/hybrid smoke + permissions | smoke parity within delta; artifact completeness | hosted iOS variance, signing wrappers |
| Cloud web | Browser cloud sanity (desktop/mobile web) | provider creds, browser matrix caps | web page | Chromium/Firefox/WebKit smoke + mobile emulation | pass parity with local web smoke | browser cloud config variance |

## 5) Web validation plan

Scope:
- Engines: Chromium, Firefox, WebKit.
- Desktop and mobile emulation profiles.
- Static web validation page with deterministic fixtures.

Planned scenario set:
1. Simple page text target and button action.
2. Duplicate label disambiguation.
3. Modal open/close and in-modal action.
4. Form field by human label.
5. Same-row action (relational targeting).
6. Report output verification (safe analytics fields, no raw dumps).

Pass expectations:
- consistent candidate selection behavior across engines,
- smoke suite >=95% pass in local reruns,
- reporting includes expected diagnostics metadata and omits unsafe payloads.

## 6) Android emulator validation plan

Setup baseline:
- Appium server reachable locally.
- UiAutomator2 automation backend.
- Android emulator image (stable API level baseline).
- One native Android sample app + one hybrid Android sample app.

Validation coverage:
- native text/content-desc/resource-id targeting,
- permission dialog detection flow,
- scroll + repeated list/card scenario,
- icon-only/weak label fallback behavior,
- framework detection assertions,
- `webview_switch_diagnostics` dry-run assertions,
- `webview_switch_guardrails` decision assertions.

Pass expectations:
- all defined emulator smoke scenarios pass,
- metadata keys present and safe,
- no runtime switching attempts (`switch_attempted` remains false in diagnostics/guardrails).

## 7) iOS simulator validation plan

Setup baseline:
- Xcode simulator runtime installed.
- Appium with XCUITest driver.
- Native iOS sample app + hybrid/WebView sample app.

Validation coverage:
- iOS attribute targeting (`label`, `name`, `value`),
- `XCUIElementType*` hierarchy recognition,
- permission dialog handling detection path,
- scroll/repeated elements and weak label cases,
- framework detection assertions,
- WebView dry-run diagnostics/guardrails checks.

Pass expectations:
- iOS smoke set green on simulator baseline,
- stable metadata/report output,
- no runtime context switching behavior introduced.

## 8) Real Android device validation plan

Setup:
- USB debugging enabled + trusted host.
- Stable adb visibility and Appium connectivity.
- Controlled device list with at least two screen classes (small/large).

Focus areas:
- real-device timing and transient delays,
- soft keyboard overlap/auto-focus behavior,
- permission dialogs across OS versions,
- WebView context availability variability,
- screen-density and viewport differences.

Pass/fail criteria:
- pass if smoke suite >=90% across N repeated runs/device and failures are diagnosable non-systemic flakes,
- fail if repeated nondeterministic misses in core target groups, unsafe metadata leaks, or unbounded flake in permission/WebView scenarios.

## 9) Real iOS device validation plan

Setup:
- provisioning/signing artifacts prepared,
- WebDriverAgent build/deploy reproducible,
- trusted device pairing and automation permissions.

Focus areas:
- WDA session stability,
- iOS permission dialog patterns,
- keyboard open/close/input side effects,
- hybrid/WebView presence and context metadata behavior.

Pass/fail criteria:
- pass if native + hybrid smoke >=90% across repeated runs with stable WDA startup success,
- fail if signing/WDA instability blocks reliable runs or hybrid diagnostics are inconsistent.

## 10) Cloud validation plan

Device farm strategy:
- begin with smallest representative matrix (one modern + one older OS each for Android/iOS),
- expand only after baseline parity.

Smoke coverage groups:
- Android native smoke,
- Android hybrid smoke,
- iOS native smoke,
- iOS hybrid smoke,
- web browser smoke.

Cloud-specific requirements:
- collect run logs, device logs, and sanitized Bubblegum reports,
- retain capability snapshot for reproducibility,
- secrets via CI secret store only (never committed),
- no hardcoded credentials, no plaintext token logging.

Pass expectations:
- cloud smoke outcome within agreed delta vs local smoke,
- artifact completeness sufficient for triage.

## 11) Test scenario catalog

Define and track scenario groups:
1. native text target,
2. accessibility/content-desc target,
3. resource-id target,
4. iOS label/name/value target,
5. WebView/hybrid context detection,
6. system dialog detection,
7. scroll/off-screen target,
8. repeated card/list target,
9. icon-only/weak label target,
10. relational target (same row/card/modal association),
11. report/analytics verification.

Each environment run should declare which groups are in-scope and report pass/fail by group.

## 12) Smoke vs regression split

- **Smoke suite (per PR/nightly target):** minimal deterministic scenarios per environment class, fast runtime, triage-focused.
- **Extended regression (release candidate):** broader device/OS/browser matrix with repeated runs and flake accounting.
- **Pre-alpha full validation:** required real-device + cloud execution across native/hybrid + reporting checks before enabling real switching implementation.

## 13) Required sample apps/pages (requirements only)

Recommend defining (not implementing in this phase):
- simple static web test page,
- simple Android native sample app,
- simple Android hybrid sample app,
- simple iOS native sample app,
- simple iOS hybrid sample app,
- optional cloud-compatible packaged sample builds.

Requirements for all samples:
- deterministic IDs/labels/accessibility hooks,
- explicit permission-dialog trigger flow,
- repeated list/card + icon-only actions,
- modal/form/relational fixtures,
- no production data dependencies.

## 14) Data and privacy rules

Validation runs must enforce:
- no real user data,
- no production apps in initial phases,
- no raw screenshots in reports unless explicitly configured,
- no raw XML/DOM dumps in report surfaces,
- no raw context names/package/process leaks,
- safe metadata only (tokens/enums/counts/warnings).

## 15) Execution commands placeholder (future)

Planned placeholders (non-binding, not implemented here):
- `python -m pytest -m smoke_web_local`
- `python -m pytest -m smoke_android_emulator`
- `python -m pytest -m smoke_ios_simulator`
- `python -m pytest -m smoke_cloud`

Optional wrapper placeholders:
- `make smoke-web`
- `make smoke-android-emu`
- `make smoke-ios-sim`
- `make smoke-cloud`

## 16) Entry criteria before real WebView switching

All must be green before any `driver.switch_to.context` implementation phase:
1. unit tests green for detector/diagnostics/guardrails,
2. guardrail metadata contract stable and sanitized,
3. Android emulator dry-run validation green,
4. iOS simulator dry-run validation green,
5. JSON/HTML reporting analytics checks green,
6. no context pollution observed in dry-run flows,
7. restore policy behavior verified with fake driver tests.

## 17) Exit criteria for real environment validation

Validation phase is complete when:
- smoke suites pass on web local + Android emulator + iOS simulator,
- repeated-run pass thresholds met on one real Android and one real iOS device,
- cloud smoke passes on minimal Android/iOS/web matrix,
- report outputs verified safe and complete,
- flake rate documented and below agreed threshold,
- open blocking issues triaged with mitigation owner and timeline.

## 18) Risks and mitigations

- **Appium flakiness:** mitigate with retries at harness layer, repeated-run baselines, and flake dashboards.
- **Device timing variance:** explicit waits, stability markers, and timing telemetry.
- **WebView context not appearing:** precondition checks + deferred/unsupported handling and fallback paths.
- **Chromedriver mismatch:** version pinning strategy and compatibility matrix checks.
- **iOS signing/WDA issues:** reproducible signing docs, WDA health prechecks, and fallback device pool.
- **Cloud device differences:** minimal matrix first, capability snapshots, provider-specific adapters/config profiles.
- **Permission dialog variance:** dedicated scenario group across OS versions with resilient dialog recognition.
- **Context restore risk (future switching):** keep switching out-of-scope until restore-policy prerequisites are met in dry-run + fake-driver testing.

## 19) Recommended next phases

Recommended strict order:
1. **Phase 19M-L — Real Environment Smoke Harness Design**
2. **Phase 19M-M — Android Emulator Smoke MVP**
3. **Phase 19M-N — iOS Simulator Smoke MVP**
4. **Phase 19M-O — Cloud Device Smoke Plan**
5. **Then** WebView Switching MVP implementation **only after** sufficient validation signal from phases above.

## GO / NO-GO

**GO for Phase 19M-L** (smoke harness design).

Rationale:
- Current metadata/dry-run foundation is strong locally.
- Real-environment validation scaffolding is the next safe prerequisite.
- Real runtime switching remains intentionally deferred.
