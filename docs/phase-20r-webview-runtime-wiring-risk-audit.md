# Phase 20R — WebView Runtime Wiring Risk Audit (Design-Only)

## 1) Purpose

This document is the final risk audit before any fake/opt-in runtime wiring for WebView switching in `validate`/`extract_text`.

It confirms the current safety foundation, codifies runtime invariants and return-policy expectations, and defines GO/NO-GO criteria for the next implementation phase while preserving default-off behavior.

## 2) Current foundation

Current implementation already provides a design-safe baseline:

- **WebView diagnostics**: `webview_switch_diagnostics` is available and reporting-safe.
- **Guardrails**: WebView and system-dialog guardrails are already evaluated and surfaced as safe metadata.
- **Eligibility**: deterministic eligibility decisions exist (`allowed`/`blocked`/`deferred`/`unknown`) with evidence/warnings.
- **Context selection**: deterministic selection helper is available with policy-based outcomes and sanitized context type.
- **Execution guard/restore helper**: `webview_switch_execution` plan + guarded switch/restore callback flow exists for fake-wiring phases.
- **Config default-off**: switching is disabled unless explicitly enabled and operation-allowed.
- **Validate/extract skeleton hooks**: adapter currently prepares wiring-plan metadata for `validate`/`extract_text` without performing runtime switching.
- **Wiring-plan reporting**: reporting pipeline can include sanitized `webview_switch_wiring_plan` and `webview_switch_execution` metadata channels.

## 3) Non-goals

This phase intentionally does **not** implement runtime behavior changes:

- No runtime switching implementation.
- No `driver.switch_to.context` usage.
- No real WebView context switching.
- No resolver priority/order changes.
- No ranker/scoring/confidence behavior changes.
- No `execute` wiring.

## 4) Runtime invariants

The following invariants must hold for next-phase fake wiring and later real wiring:

1. Default configuration means **no switch attempt**.
2. Only `validate` and `extract_text` are candidates for first MVP runtime wiring.
3. `execute` remains unwired.
4. Restore is required after any successful switch.
5. Restore failure is fail-closed.
6. Raw context names are never reported.
7. Metadata is always sanitized.

## 5) Risk matrix

| Risk | Impact | Likelihood | Mitigation | Test coverage needed |
|---|---|---|---|---|
| Wrong WebView selected | High | Medium | Deterministic selection policy; block/defer on ambiguity; no implicit fallback to random context | Multi-WebView selection policy tests; ambiguous selection blocked/deferred tests |
| Restore failure | High | Medium | Mandatory restore attempt after switch; fail-closed on restore failure | Restore-failure fail-closed tests with execution metadata assertions |
| Switch succeeds but operation fails | Medium | Medium | Preserve operation failure semantics; still enforce restore attempt | Operation-failure-after-switch tests validating restore attempted |
| Operation succeeds but restore fails | High | Low/Medium | Safety override: restore failure supersedes operation success | “Success then restore fail” tests asserting safety failure status |
| WebView not ready | Medium | Medium/High | Eligibility/selection block or defer; bounded retries in later phases only if policy-approved | Not-ready blocked/deferred tests; no unsafe retries |
| Stale WebView context | Medium/High | Medium | Treat as switch/operation failure with safe reason classification; enforce restore behavior | Stale-context failure tests with metadata sanitization checks |
| System dialog appears mid-switch | High | Medium | Dialog guardrails gate switching; abort/defer with safety metadata | Dialog-blocking tests before and during fake-switch path |
| Hidden native modal | High | Low/Medium | Conservative failure/defer policy; no blind retries; preserve native safety | Modal interference simulations ensuring fail-closed/defer behavior |
| Multiple WebViews | Medium/High | Medium | Deterministic policy (`single_webview_only`, hint policy); no auto-pick on ambiguity | Multi-WebView policy tests for selected vs blocked/deferred outcomes |
| Cloud provider context variance | Medium | Medium | Keep default-off and fake-only first; phase cloud trials after local confidence | Provider-variance contract tests and optional cloud smoke checklist |
| iOS context behavior variance | Medium | Medium | Require iOS-specific readiness gate before real switching | iOS simulator readiness smoke criteria and parity tests |
| Accidental execute wiring | High | Low | Explicit non-goal; unit tests asserting `execute` path remains unwired | Tests that execute does not invoke switch guard/switch logic |
| Metadata leakage | High | Low/Medium | Strict sanitization and safe enums/tokens only; never emit raw context names | JSON/HTML metadata redaction tests for wiring and execution metadata |

## 6) Validate/extract return policy

Future fake/opt-in runtime behavior should follow this policy:

- `validate` should fail closed if switch/restore safety fails.
- `extract_text` should return a safe failed/empty result if switch/restore safety fails.
- Operation failure after successful switch must still preserve restore attempt.
- Restore failure overrides operation success as a safety failure.
- Metadata should always include `webview_switch_execution`.

## 7) Fake switch wiring acceptance criteria

Before any real driver switching is considered, all of the following must be true:

1. Fake switch success path tested.
2. Fake switch failure path tested.
3. Fake restore failure path tested.
4. Default-off no-op path tested.
5. Operation failure after switch tested.
6. Metadata/reporting behavior tested.
7. No execute wiring tested.

## 8) Real switching readiness criteria

Before introducing `driver.switch_to.context` in a later phase:

1. Fake wiring is complete.
2. Reporting contract is complete.
3. Android local/emulator WebView test app is available.
4. iOS simulator WebView app/sample is available.
5. Restore behavior is proven under failure scenarios.
6. Cloud provider trial is optional but preferred.

## 9) Test plan for next phase (20S or next implementation phase)

Recommended tests:

- Default-off no-op `validate`.
- Default-off no-op `extract_text`.
- Opt-in fake `validate` switch success.
- Opt-in fake `extract_text` switch success.
- Switch failure handling.
- Restore failure handling.
- Operation failure after switch.
- Metadata redaction/sanitization.
- `execute` remains unwired.

## 10) GO/NO-GO recommendation

**Recommendation: GO for next implementation phase only if all constraints are preserved:**

- Fake-only wiring.
- `validate`/`extract_text` only.
- Default-off behavior.
- No `driver.switch_to.context` usage.
- Restore fail-closed policy.
- Reporting metadata attached (`webview_switch_execution`, sanitized).

If any requirement cannot be guaranteed, recommendation is **NO-GO** until corrected.
