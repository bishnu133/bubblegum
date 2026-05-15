# Phase 19M-I — WebView Real Switching Design Review (Design-Only)

## 1) Problem statement

Real WebView context switching is needed because dry-run diagnostics can only predict when switching *might* help; they cannot resolve or interact with elements that are only reachable through an active `WEBVIEW_*` context. In hybrid apps, native hierarchy parsing alone can miss actionable DOM-backed targets, especially for action, verify, and extract operations where web-layer semantics are required.

Dry-run diagnostics do not solve:
- actual element lookup/execution in WebView,
- confirmation that WebView DOM is automation-ready at runtime,
- real fallback/restore behavior under exceptions.

Switching is risky and must be tightly controlled because it can introduce session-state pollution, stale contexts, system-dialog interruptions, and non-deterministic behavior if context transitions are not reversible and auditable.

## 2) Current foundation summary

Current baseline already provides the minimum design prerequisites:

- **`context_inventory` metadata** in `UIContext.app_state` from Appium adapter, including sanitized context types, counts, inferred mode, and warnings.
- **`framework_detection` metadata** with surface classification (`android_native`, `ios_native`, `webview`, `hybrid`, `system_dialog`, `unknown`), evidence tokens, confidence, and safe-metadata guarantees.
- **`webview_switch_diagnostics` (dry-run only)** with `status`, `recommended_context`, `switch_required_future`, and reasons/evidence; `switch_attempted` is currently always `false`.
- **Reporting/analytics visibility** in JSON/HTML via safe metadata extraction and redaction helpers, including explicit unsafe-key blocking.
- **Current Appium behavior remains native-hierarchy based** (`page_source` capture + native resolver behavior) with no live context switching.

This foundation is sufficient for policy finalization prior to runtime implementation.

## 3) Non-goals (Phase 19M-I)

- No implementation of real switching in adapter/resolvers.
- No runtime calls to `driver.switch_to.context`.
- No resolver routing or priority/order changes.
- No ranker/scoring/confidence changes.
- No public API/schema changes.
- No new dependencies.

## 4) Proposed future switching policy

### 4.1 When switching is allowed
Switching is allowed only if **all** are true:
1. Explicit runtime opt-in is enabled (default remains off).
2. Surface is `webview` or `hybrid`.
3. Dry-run diagnostics status is `webview_candidate` or `hybrid_candidate`.
4. At least one WebView context is present (`has_webview_context=true`).
5. Operation is `action`, `verify`, or `extract` **and** target hints are web-like.
6. Original context can be captured deterministically.

### 4.2 When switching is blocked
Switching is blocked if any of the following hold:
- Surface is `android_native`, `ios_native`, `system_dialog`, or `unknown`.
- No WebView context inventory is available.
- Runtime policy is opt-out/default mode.
- Current step is system-dialog handling or unknown-surface recovery.

### 4.3 When switching is deferred
Mark deferred and stay native when:
- context inventory is ambiguous/incomplete,
- multiple WebViews exist without deterministic selection signal,
- prior step marked webview environment unstable.

### 4.4 Fallback-to-native policy
Fallback to native immediately when:
- context lookup/switch throws,
- selected WebView becomes stale,
- DOM/automation snapshot is unavailable after switch,
- target lookup fails in WebView and native remains viable.

### 4.5 Return-unsupported policy
Return unsupported (without switching) when:
- no WebView context exists despite webview/hybrid indicators,
- capabilities/environment cannot support web automation path,
- policy gate disallows switching for this run mode.

## 5) Context safety rules

Mandatory guardrails for future implementation:
1. Always capture and store original context type before any switch attempt.
2. Attempt switch only if at least one WebView context exists.
3. Always attempt restore to original context after WebView probe/execute (success or failure).
4. Never leave session in changed context on failure paths.
5. Fail closed (`deferred`/`unsupported`) on ambiguous context state.

## 6) Candidate switching scenarios

- **native_only**: block switching; resolve native.
- **webview_only**: allowed only with opt-in and actionable web-like step; else deferred.
- **hybrid**: candidate for guarded switch; prefer WebView only when policy gates pass.
- **system_dialog**: block switching; native/system-safe handling only.
- **unknown**: block switching; fail closed.
- **stale WebView context**: mark `stale`, fallback native, emit warning.
- **context lookup failure**: mark `unsupported` or `deferred` (policy-defined), fallback native.
- **switch failure**: mark `failed`, attempt restore, fallback native.
- **DOM unavailable after switch**: mark `failed`/`deferred`, restore, fallback native.

## 7) Resolver strategy review

- **Option A — switch before resolver selection**: simple but high risk of unnecessary switching and state churn.
- **Option B — native resolver first, then WebView resolver**: safer incremental behavior, but may miss WebView-first intent latency-wise.
- **Option C — dry-run both surfaces, then choose**: strongest control/auditability; aligns with existing diagnostics foundation.
- **Option D — explicit user opt-in only**: strongest governance, but alone does not define arbitration.

### Recommended MVP strategy
Recommend **Option C + Option D combined**:
- keep explicit opt-in gate (D),
- use dry-run-informed dual-surface decisioning (C) before any real switch attempt.

This preserves determinism and minimizes false-positive switching.

## 8) Recommended MVP approach

For the future implementation phase, MVP should be:
- opt-in only (default off),
- limited to `webview`/`hybrid` surfaces,
- enabled only when dry-run says `webview_candidate` or `hybrid_candidate`,
- attempted only for `action`/`verify`/`extract` with web-like target hints,
- never auto-switch for `system_dialog` or `unknown`.

## 9) Safe metadata to emit (future runtime)

Runtime-safe metadata contract (internal/additive):
- `switch_attempted` (bool)
- `switch_status` (`not_attempted|success|failed|stale|unsupported|deferred`)
- `original_context_type` (`native|webview|webview/chromium|other|unknown`)
- `selected_context_type` (`native|webview|unknown`)
- `restore_attempted` (bool)
- `restore_status` (`not_needed|success|failed`)
- `fallback_reason` (enum-like label)
- `warnings` (safe labels)
- `safe_metadata_only` (always true)

## 10) Privacy/sanitization design

Future implementation must continue strict sanitization:
- no raw DOM,
- no raw XML,
- no screenshot bytes,
- no raw context names,
- no package/process names,
- no provider payload bodies,
- no exception traces.

Only compact enums/tokens/booleans/counts may be emitted.

## 11) Failure handling policy

- **No WebView context**: return `unsupported`; remain native.
- **Multiple WebView contexts**: deterministic selection required; otherwise `deferred` and native fallback.
- **Context switch exception**: status `failed`; restore attempt mandatory; native fallback.
- **DOM unavailable**: status `failed` or `deferred`; restore; native fallback.
- **Element not found in WebView**: restore; continue native fallback path if applicable.
- **Restore failure**: mark critical warning and fail closed for the step/session policy.
- **System dialog interruption**: abort WebView flow, restore if needed, route to system-dialog-safe path.

## 12) Test strategy for future implementation

Use fake Appium drivers and unit tests only:
- verify switch is called only when policy allows,
- verify original context is restored on success,
- verify restore is attempted on switch/DOM/lookup failures,
- verify no switch for `native_only`, `system_dialog`, `unknown`,
- verify multi-WebView handling is deterministic or safely deferred,
- verify diagnostics metadata emission (`switch_status`, restore/fallback fields),
- verify no raw context names leak into reports/metadata.

No real Appium server, browser, OpenAI, or network dependency in tests.

## 13) Benchmark strategy

Current 34 object-intelligence seed cases are sufficient to preserve regression coverage for resolver behavior while implementing switching guardrails, because they already exercise ambiguity/disambiguation/fallback patterns and reporting metadata flows.

Before real switching rollout, add fixture coverage for:
- multi-WebView selection disambiguation,
- stale WebView lifecycle,
- WebView-first target with native fallback,
- system-dialog interruption during switching.

These can be synthetic/fake-driver fixtures without live Appium execution.

## 14) Risk assessment

- **Flakiness risk**: medium-high if readiness checks are weak.
- **Session state pollution risk**: high without strict restore guarantees.
- **WebView driver readiness risk**: medium-high (depends on runtime availability/timing).
- **Chromedriver compatibility risk**: high in mixed Android environments.
- **False-positive WebView switching risk**: medium; mitigated by opt-in + dry-run gate.
- **Restore failure risk**: high impact; must fail closed and emit critical warnings.

## 15) Recommendation

### Decision
**GO** for next implementation preparation phase, with guardrail-first scope.

### Recommended next phase
**Phase 19M-J — WebView Switching Metadata-Only Guardrails**.

### Scope for 19M-J
- implement metadata-only runtime decision/guardrail plumbing (still no actual `switch_to.context`),
- finalize deterministic status enums/reasons,
- add unit tests for allow/block/defer/fallback decision matrix,
- validate JSON/HTML sanitization for future switching fields.

Rationale: this is the safest direct prerequisite to real switching, lower risk than jumping into system dialog or memory-signature tracks first.

---

## Explicit phase compliance

This Phase 19M-I output is design documentation only and does **not** introduce runtime context switching behavior.
