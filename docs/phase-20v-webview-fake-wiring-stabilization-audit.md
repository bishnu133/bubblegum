# Phase 20V — WebView Fake Wiring Stabilization Audit

## 1. Purpose

This Phase 20V audit closes the fake-wiring stabilization track for WebView switching and establishes readiness criteria for the next design-focused phase.

Scope for this document is intentionally limited to audit and documentation: it confirms current fake wiring behavior for `validate`/`extract`, verifies fail-closed and metadata-safety properties, and captures residual gaps before any real-driver context switching design.

This phase is the final checkpoint before **Phase 20W — Real Driver WebView Switching Design Review**.

## 2. Current fake-wiring foundation

The current foundation is in place and consistent with Phase 20S/20T/20U objectives:

- **Config default-off behavior exists** via config gating and operation allowlisting.
- **Eligibility evaluator is integrated** and consumed as metadata input to wiring readiness.
- **Context selection helper is integrated** and consumed as metadata input to wiring readiness.
- **Wiring-plan metadata exists** and normalizes readiness/reason fields with safe metadata markers.
- **Execution guard/restore helper exists** with explicit switch/restore status tracking and fail-closed semantics.
- **Validate/extract fake wiring exists** and is activated only by injected fake callables plus explicit readiness.
- **Reporting/analytics exists** in JSON/HTML with redaction-compatible rendering and switch/restore counters.
- **Failure-matrix tests are expanded** across switch failure, restore failure, operation failure, context-read failure, and missing restore callable behavior.
- **`execute` remains unwired** for WebView switching.

## 3. Safety invariants

The following safety invariants are currently satisfied:

- No runtime use of real `driver.switch_to.context` in the mobile implementation path.
- Switching uses **injected callables only** (`get_current_context`, `switch_context`, `restore_context`).
- Default configuration behavior remains **no-op** (non-opt-in usage does not switch).
- Fake switch execution applies to **validate/extract only**.
- `execute` is explicitly unwired for fake switch execution.
- Restore behavior is fail-closed for user-facing outcomes where safety could be compromised.
- Metadata is sanitized to safe enums/reasons and redacted execution error signaling.
- Raw context names are not leaked in failure metadata/reporting paths.

## 4. Test coverage summary

Coverage currently documents and enforces:

- Default no-op behavior.
- Opt-in success path with switch then restore.
- Switch failure handling.
- Restore failure handling.
- Operation failure after successful switch with restore attempt behavior.
- `get_current_context` failure handling and sanitization.
- Missing restore callable behavior (`restore_status="unknown"`).
- Invalid extract result handling with safe fallback behavior.
- JSON/HTML reporting compatibility for `webview_switch_execution` payloads.
- Analytics counters for switch/restore statuses and failure events.
- Execute path remains unwired.

## 5. Remaining gaps before real switching

The following gaps remain and are intentionally deferred to real-driver phases:

- Real driver context API is not yet used.
- Real WebView context identifiers/names require safe mapping policy.
- Android WebView sample app coverage is still needed.
- iOS WebView sample app coverage is still needed.
- Cloud provider context semantics/availability are not yet validated.
- Restore-failure behavior with real drivers is unproven.
- Hybrid timing / stale WebView behavior under real sessions is unknown.
- Operation execution inside real WebView contexts is not yet real-driver validated.

## 6. Risk assessment before real-driver design

Primary risks to address in design review:

- Wrong context selection (including false-positive WebView selection).
- Restore failure that leaves session in incorrect context.
- Hybrid app timing races during context availability transitions.
- Stale context references between selection and switch.
- System dialog interruption during switch/restore windows.
- iOS context naming/variance across drivers.
- Cloud provider variance in context enumeration and switching semantics.
- Accidental future expansion into `execute` wiring without explicit design controls.
- Metadata leakage regressions if real context identifiers are surfaced unsafely.

## 7. GO/NO-GO recommendation

**Recommendation: GO for Phase 20W (design review only),** contingent on all of the following remaining true:

- Fake-wiring unit tests pass.
- Reporting tests (JSON/HTML WebView switch reporting + analytics) pass.
- Default-off behavior remains preserved.
- No runtime usage of `switch_to.context` exists.
- `execute` remains unwired.

If any condition above regresses, recommendation is **NO-GO** until corrected.

## 8. Proposed next sequence

Recommended sequence:

1. **20W — Real Driver WebView Switching Design Review**
2. **20X — Real Driver Switch Helper Skeleton (not wired)**
3. **20Y — Strict Opt-in Validate/Extract Real Switching MVP**
4. **20Z — Android WebView Real-Env Smoke**
5. **21A — iOS WebView Real-Env Smoke**

---

### Audit conclusion

The fake-wiring track is stable for design handoff: validate/extract fake execution paths are guarded, sanitized, fail-closed, and covered by targeted failure-matrix plus reporting analytics tests; `execute` remains intentionally unwired.
