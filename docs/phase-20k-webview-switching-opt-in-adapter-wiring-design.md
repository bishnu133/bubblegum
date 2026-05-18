# Phase 20K — WebView Switching Opt-in Adapter Wiring Design (Design-Only)

## 1) Purpose

This phase defines the adapter wiring design before implementation so Phase 20L+ can add WebView switching in a controlled, fail-closed, and test-first way.

A dedicated design step is required because wiring affects critical runtime paths (`execute`, `validate`, `extract_text`) and must preserve current guarantees:

- default behavior remains unchanged (no automatic switching),
- context safety and restoration remain mandatory,
- metadata remains sanitized,
- hybrid/mobile variability is handled with explicit policy gates.

By freezing the wiring contract first, implementation phases can avoid accidental behavior drift in resolver/ranker/memory paths and keep rollout opt-in.

## 2) Current foundation

The existing foundation already provides most primitives needed for future safe wiring:

- **`webview_switch_diagnostics`**: classifies candidate status (for example, WebView/hybrid candidacy) without forcing live switching.
- **`webview_switch_guardrails`**: supplies allow/block/defer signals and policy evidence.
- **`webview_switch_eligibility`**: evaluates explicit opt-in, surface type, diagnostics, system dialog blocking, and WebView availability into deterministic decisions.
- **`webview_context_selection`**: applies policy-based selection (`single_webview_only`, `first_available`, `hint_match`) and returns selected/deferred/blocked.
- **`webview_switch_execution` helper**: builds execution plans and supports guarded switch/restore callback orchestration with sanitized metadata.
- **Reporting/analytics support**: JSON/HTML reporting already supports sanitized WebView switch metadata emission patterns.
- **Android/iOS/cloud real-env harnesses**: skip-gated harnesses exist for later opt-in smoke validation across environments.

## 3) Non-goals

This phase is design-only and intentionally makes **no runtime changes**.

- No implementation in this phase.
- No `driver.switch_to.context` call introduction.
- No default automatic switching.
- No resolver/ranker/scoring/confidence changes.
- No memory lookup behavior changes.
- No cloud execution behavior changes.

## 4) Future config design

Future phases should add explicit, minimal, opt-in config with safe defaults:

- `enable_webview_switching: false` (default off)
- `webview_switching_mode: off | dry_run | opt_in`
- `webview_switch_allowed_operations: action | verify | extract` (operation-level allowlist)
- `require_restore_context: true`
- `fail_closed_on_restore_failure: true`
- `webview_context_selection_policy: single_webview_only | first_available | hint_match`
- `max_webview_switch_attempts: 1`

Design notes:

- `enable_webview_switching=false` and `webview_switching_mode=off` should both keep current no-op behavior.
- `dry_run` should allow diagnostics/metadata flow without live switching.
- `opt_in` should still require eligibility + selection + operation allowlist, not just a single flag.

## 5) Future wiring entry points

Possible future wiring points:

- `AppiumAdapter.execute`
- `AppiumAdapter.validate`
- `AppiumAdapter.extract_text`
- SDK `act`/`verify`/`extract` orchestration layer

### Recommended safest MVP entry point

Start with **`validate` and `extract_text`** (or explicitly marked `action` cases only), not all actions by default.

Rationale:

- `validate`/`extract_text` are generally lower-risk than broad action routing.
- Limits blast radius while proving switch/restore reliability.
- Supports incremental rollout before enabling wider action coverage.

## 6) Wiring policy

Future wiring should execute only when **all** conditions are true:

1. Channel is mobile.
2. Explicit config opt-in is enabled (`enable_webview_switching=true` and mode allows switching).
3. Eligibility decision is `allowed`.
4. Context selection decision is `selected`.
5. Operation type is explicitly allowed by `webview_switch_allowed_operations`.
6. No system dialog blocking is present.
7. Guard/restore helper path is available.
8. Target/reference semantics indicate WebView-compatible intent.

If any condition fails, do not switch and preserve existing native/default flow.

## 7) Block/defer behavior

Future policy should block or defer switching when:

- opt-in is missing,
- surface is native-only,
- no selected WebView exists,
- multiple WebViews remain unresolved,
- system dialog is active,
- restore risk is detected,
- selected operation type is not allowed,
- current target is native-only.

Suggested mapping:

- **Blocked**: hard safety/policy disallow.
- **Deferred**: ambiguity or timing condition that may become resolvable.

## 8) Execution flow design

Future opt-in execution flow should be:

1. Collect current context (safe normalized type + opaque restore handle).
2. Evaluate eligibility.
3. Select WebView context per configured policy.
4. Build execution plan metadata.
5. Execute guarded switch.
6. Run operation in WebView context.
7. Restore original context (required).
8. Attach `webview_switch_execution` metadata to `StepResult`.
9. Fail closed on restore failure.

Important: restore is mandatory when switching is attempted, regardless of operation outcome.

## 9) Failure handling

Future implementation should define deterministic handling for:

- **Switch failure**: mark switch failed, sanitize exception reason, avoid unsafe retries beyond configured attempts.
- **Operation failure after switch**: preserve operation failure outcome, still attempt restore, annotate metadata.
- **Restore failure**: fail closed when `fail_closed_on_restore_failure=true`.
- **Timeout**: treat as failure with sanitized timeout reason.
- **Stale WebView context**: convert to safe classified failure reason (no raw context leak).
- **Unexpected native/system dialog during switch**: abort/defer and prioritize safety.
- **Exception sanitization**: never expose raw driver internals or sensitive payloads.

## 10) Metadata/reporting behavior

Future wiring must:

- attach `webview_switch_execution` metadata to step outputs,
- reuse existing report sanitization flows,
- avoid raw context names,
- avoid raw XML/source/screenshots/secrets in WebView switch fields.

Only normalized enums, reasons, counts, and safe evidence tokens should be reported.

## 11) Test strategy

Implementation phases should include:

- fake driver unit tests,
- adapter-level tests with fake switch-context API,
- config-off no-op tests,
- opt-in success tests,
- restore failure tests,
- operation failure tests,
- JSON/HTML report tests (already covered by Phase 20J behavior patterns),
- later real-env Android/iOS opt-in smoke tests.

Cloud/provider live switching should remain out of MVP until mobile local confidence is established.

## 12) Risk assessment

Primary risks and mitigations:

- **Wrong context selection** → deterministic policy + block/defer on ambiguity.
- **Restore failure** → mandatory restore + fail-closed behavior.
- **Hidden native/system dialog** → dialog-aware blocking/defer checks before/around switching.
- **Hybrid app instability** → attempt cap (`max_webview_switch_attempts=1`) and strict fallback.
- **Cloud/provider context differences** → defer cloud switching rollout until later phases.
- **WebView timing/loading delays** → timeout classification + no unsafe repeated switching.
- **Accidental native action in WebView** → operation allowlist + explicit target compatibility checks.

## 13) Recommended implementation sequence

Recommended next phases:

1. **20L — Config + Wiring Skeleton, no real switching by default**
2. **20M — Adapter Wiring Unit Tests with fake switch API**
3. **20N — Opt-in MVP Adapter Wiring**
4. **20O — Android WebView Opt-in Smoke**
5. **20P — iOS WebView Opt-in Smoke**

## 14) GO/NO-GO

Recommendation: **GO for 20L only** if implementation preserves all of the following:

- default off,
- explicit opt-in required,
- restore required,
- fail closed on restore/safety failures,
- no raw context leakage.

If any of the above cannot be guaranteed in 20L scaffolding, recommendation is **NO-GO** until corrected.
