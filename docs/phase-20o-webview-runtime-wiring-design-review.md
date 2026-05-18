# Phase 20O — WebView Runtime Wiring Design Review (Design-Only)

## 1) Purpose

This document is the final design review before opt-in runtime WebView wiring is implemented. It consolidates the current safety foundation, defines the required gating and restore contracts, and sets a phased rollout path that preserves default-off behavior while minimizing runtime risk.

## 2) Current implementation foundation

The codebase already includes the critical primitives needed for safe runtime wiring:

- **Diagnostics**: `webview_switch_diagnostics` classifies WebView/hybrid candidacy and emits safe evidence-only metadata.
- **Guardrails**: `webview_switch_guardrails` and dialog guardrails provide policy-level allow/defer/block inputs before any switch attempt.
- **Eligibility**: deterministic eligibility evaluation exists, including opt-in presence, surface eligibility, diagnostics candidacy, guardrails status, system dialog blocking, and WebView availability.
- **Context selection**: deterministic context-selection helper supports `single_webview_only`, `first_available`, and `hint_match` with blocked/deferred/selected outcomes.
- **Execution guard/restore helper**: `webview_switch_execution` plan builder + guarded execution callback flow supports switch attempt tracking, restore attempt tracking, and safe metadata.
- **Config skeleton**: WebView switching config is present and default-off, with operation-level gating and mode checks.
- **Adapter wiring-plan metadata**: Appium adapter currently prepares/sanitizes `webview_switch_wiring_plan` metadata without enabling runtime switching.
- **Reporting/analytics**: JSON and HTML reporting sanitize and emit WebView switching metadata channels (`diagnostics`, `eligibility`, `selection`, `execution`, `wiring_plan`) without raw sensitive payloads.
- **Real-env harnesses**: local/emulator/simulator/cloud-oriented harness structure exists with skip-by-default behavior for later opt-in smoke phases.

## 3) Non-goals

This phase intentionally does **not** change runtime behavior.

- No runtime wiring implementation in this phase.
- No `driver.switch_to.context` usage added.
- No runtime WebView switching enabled.
- No `AppiumAdapter.execute`, `AppiumAdapter.validate`, or `AppiumAdapter.extract_text` runtime-switch behavior changes.
- No resolver priority/order changes.
- No ranker/scoring/confidence changes.
- No memory lookup behavior changes.

## 4) Proposed runtime entry point

Compared entry points:

- **`AppiumAdapter.execute`**: highest blast radius; broad action surface; greater risk of accidental native/web mismatch.
- **`AppiumAdapter.validate`**: narrower semantics, generally read/verify oriented, lower interaction risk.
- **`AppiumAdapter.extract_text`**: similarly narrow/read-oriented and safer for early runtime proofing.
- **SDK orchestration layer**: broader cross-adapter implications; increased coupling and larger rollback surface.

### Recommendation

Safest MVP entry point is:

1. **Start with `validate` and `extract_text` only** under strict opt-in.
2. Defer broad `execute` wiring until a later phase.
3. Allow `execute` only for explicitly marked WebView-compatible actions, still gated by strict opt-in and fail-closed restore policy.

## 5) Runtime gating checklist

Future runtime switching must require **all** of the following:

1. `enable_webview_switching=True`
2. `webview_switching_mode == "opt_in"`
3. Operation type is explicitly allowed.
4. Eligibility decision is `allowed`.
5. Context selection decision is `selected`.
6. Selection policy is deterministic (no unresolved ambiguity).
7. System dialog is not blocking.
8. Selected WebView context is currently available.
9. Restore is required and configured.
10. Fail-closed behavior is enabled.

Any failed gate must keep default/native flow and report safe metadata only.

## 6) Proposed execution flow

Future opt-in runtime flow should be:

1. Collect current context inventory and supporting signals.
2. Prepare `webview_switch_wiring_plan` metadata.
3. Build `webview_switch_execution` plan from eligibility + selection + opt-in status.
4. Capture original context handle/type for restoration.
5. Switch to selected WebView context.
6. Run operation.
7. Restore original context.
8. Attach `webview_switch_execution` metadata to result/report payloads.
9. If restore fails, fail closed and stop further action.

## 7) Restore contract

Required restore contract:

- Restore is always attempted after any successful switch.
- Restore failure converts final step outcome to `failed`/`safety_failed` (fail-closed).
- Restore metadata is always attached, including attempted/status/reason/warnings.
- No further operation retries/actions are performed after restore failure.
- Raw context names are never emitted; only sanitized context type/evidence tokens are allowed.

## 8) Operation policy

Phased operation support policy:

- **Phase 1**: verify/extract only (`validate` + `extract_text`).
- **Phase 2**: explicitly marked safe actions only.
- **Phase 3**: broader actions only after real-env confidence and stability gates are met.

## 9) Failure policy

Future runtime implementation must explicitly handle:

- **Switch failure**: classify safe reason, do not leak raw context/provider details, no unsafe retries.
- **Operation failure after switch**: preserve operation failure, still enforce restore.
- **Restore failure**: fail closed and mark safety failure.
- **WebView not ready**: deterministic blocked/deferred/failure classification.
- **Stale context**: safe classified failure, no raw context leakage.
- **System dialog interruption**: abort/defer switching and prioritize native/system safety handling.
- **Provider/cloud differences**: keep strict guardrails and phased rollout; no implicit behavior drift.
- **Timeout**: classify safely; enforce bounded attempts.

## 10) Metadata policy

Required metadata/reporting contract:

- `webview_switch_wiring_plan` must be attached for wiring decisions.
- `webview_switch_execution` must be attached for switch/restore outcomes.
- No raw context names in metadata.
- No raw XML/source/screenshots/capabilities/secrets in WebView switch metadata.
- Evidence tokens/enums/reasons/counters only.

## 11) Testing strategy

Required future testing layers:

- Fake-driver unit tests for eligibility/selection/execution paths.
- Adapter-level default-off/no-op tests.
- Opt-in fake/injected switch API tests (success/failure).
- Restore failure fail-closed tests.
- JSON/HTML report sanitization and metadata presence checks.
- Android local/emulator opt-in smoke (later).
- iOS simulator opt-in smoke (later).
- Cloud/provider smoke (later, after local confidence).

## 12) Rollout plan

Recommended next phases:

1. **20P** — Adapter wiring skeleton behind config, no real switching.
2. **20Q** — Opt-in `validate`/`extract_text` wiring with fake/injected switch API.
3. **20R** — Real driver WebView switching behind strict opt-in.
4. **20S** — Android WebView opt-in smoke.
5. **20T** — iOS WebView opt-in smoke.

## 13) Risk assessment

Primary risks and mitigations:

- **Wrong WebView selection**: deterministic policy + defer/block on ambiguity.
- **Restore failure**: mandatory restore + fail-closed escalation.
- **Accidental native action inside WebView**: phased operation policy + explicit action eligibility.
- **WebView timing/load delay**: timeout controls and bounded attempts.
- **Hidden system dialog**: dialog blocking gates before/around switching.
- **Cloud provider context differences**: delay broader cloud rollout until local confidence.
- **Flaky hybrid apps**: incremental rollout, strict gating, and safety-first fallback.

## 14) GO/NO-GO recommendation

**Recommendation: GO for next phase only if all are preserved:**

1. Default-off behavior remains unchanged.
2. Initial runtime MVP is `validate`/`extract_text` only (or explicitly marked safe actions).
3. Restore failure is fail-closed.
4. Raw context leakage remains blocked across runtime/reporting paths.

If any condition is not guaranteed, recommendation is **NO-GO** until corrected.
