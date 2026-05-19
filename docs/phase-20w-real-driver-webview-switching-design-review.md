# Phase 20W — Real Driver WebView Switching Design Review

## 1. Purpose

This Phase 20W document is the final **design review checkpoint** before introducing any real driver context-switch helper for WebView operations.

It is intentionally design-only and defines guardrails, invariants, and rollout sequencing so that a future implementation can be added safely without regressing the stabilized fake-wiring foundation completed in Phase 20V.

## 2. Current foundation

The current system foundation (post-20V) is established and should be treated as the baseline contract:

- **Config default-off** behavior exists and prevents runtime switching unless explicitly enabled and allowed per operation.
- **Eligibility evaluator** exists and produces safe, structured allow/block/defer decisions.
- **Context selection helper** exists and provides deterministic, safe metadata outcomes (`selected_context_type`, `selected_context_index`, reason/decision).
- **Execution guard/restore helper** exists and models switch attempt + restore attempt lifecycle, including fail-closed semantics for safety-sensitive paths.
- **Validate/extract fake wiring** is in place via injected fake callables only; no real driver API is used.
- **Reporting/analytics** are integrated in JSON/HTML metadata sanitization and analytics summaries.
- **Failure matrix coverage** exists for switch/restore/get-context/operation failure branches and sanitized metadata outcomes.
- **Fake wiring stabilization audit** (20V) completed and documented as ready for design handoff.
- **Execute remains unwired** for WebView switching and must remain so until explicitly approved in a future phase.

## 3. Non-goals

This phase explicitly does **not** do any of the following:

- No implementation changes to runtime switching behavior.
- No usage of `driver.switch_to.context` in this phase.
- No `execute` wiring for WebView switching.
- No broad runtime switching expansion beyond future validate/extract MVP scope.
- No resolver priority/order changes.
- No ranker/scoring/confidence changes.
- No package version changes.
- No dependency additions or dependency upgrades.

## 4. Real driver switch helper design

Future implementation should be introduced as an isolated helper layer (not adapter-wired at first), with a minimal and auditable API shape.

Suggested helper functions (design contract):

1. `get_current_context_type(driver, *, context_inventory=None) -> dict`
   - Reads current context safely.
   - Returns only safe metadata (`native`/`webview`/`unknown`) plus sanitized status/reason fields.
   - Never emits raw context names.

2. `switch_to_selected_webview(driver, *, selected_context_index, refreshed_context_inventory) -> dict`
   - Resolves `selected_context_index` to an internal raw context name from refreshed inventory.
   - Performs the switch call internally (future phase only).
   - Returns safe status + metadata (attempted/succeeded/failed, reason, warnings).

3. `restore_original_context(driver, *, original_context_token, refreshed_context_inventory=None) -> dict`
   - Attempts to restore the pre-switch context using internally retained raw context token/name.
   - Returns safe restore status metadata only.
   - Must not emit raw names even on failure.

4. `execute_real_webview_switch_guarded(...) -> dict`
   - Orchestrates: gating -> inventory refresh -> switch -> operation -> restore.
   - Preserves fail-closed policy and metadata sanitization.
   - Compatible with existing execution metadata shape so reporting remains stable.

Design constraints:

- Helper must be isolated from adapter runtime wiring in 20X.
- Helper interfaces should be deterministic and unit-test-first.
- Raw context names are strictly internal implementation detail.

## 5. Context identity policy

Context identity handling must satisfy the following invariants:

- Raw driver context names (e.g., `WEBVIEW_com.example`) must **never** be reported.
- Real raw context names may be used **only internally** to perform driver switch/restore calls.
- Output metadata must expose only safe context descriptors:
  - `selected_context_type`
  - `selected_context_index`
  - `original_context_type`
- `selected_context_index` is a stable logical index that maps internally to the actual raw context name at runtime.
- Context inventory must be refreshed immediately before switch execution to reduce stale mapping risk.

## 6. Runtime gating policy

Real switching (future MVP) must require all of the following gates to pass:

- `enable_webview_switching=True`
- `webview_switching_mode="opt_in"`
- Operation type is **validate/extract only** for MVP
- Operation is allowlisted by config
- Eligibility decision is `allowed`
- Context selection decision is `selected`
- Deterministic context index is available
- No blocking system dialog is active
- Restore requirement is active (switch without restore is disallowed)
- `fail_closed_on_restore_failure=True`

If any gate fails, switch is not attempted and safe metadata reason is emitted.

## 7. Restore policy

Restore behavior is mandatory and safety-dominant:

- Capture original context identity/token before any switch attempt.
- Always attempt restore after any successful switch attempt, including when operation fails.
- Restore failure overrides operation success (final outcome treated as safety failure).
- No further operation steps are allowed after restore failure is detected.
- Restore metadata must always be attached (`restore_attempted`, `restore_status`, reason/warnings).
- Raw context names must not appear in output metadata, exceptions, or reports.

## 8. Failure handling policy

Future helper must explicitly handle and sanitize at least these classes:

- Get-contexts failure (`driver.contexts` retrieval fails)
- Selected index missing/out-of-range in refreshed inventory
- Switch failure (driver throws during switch)
- Operation failure after successful switch
- Restore failure
- Stale WebView context (inventory drift between collect and switch)
- WebView not ready (context present but not usable)
- Unexpected native/system dialog interruption
- Timeout during switch/operation/restore window
- Exception sanitization (no raw internals, no raw context names, no sensitive payloads)

## 9. Validate/extract MVP behavior

For the real-switch MVP scope (future phase):

- `validate`: fail-closed on switch/restore safety failures.
- `extract_text`: return safe empty/failure result contract on switch/restore safety failures.
- Operation failure after switch still must attempt restore.
- Execution metadata must always be attached for attempt/no-attempt/success/failure branches.

## 10. Test strategy

Required testing plan for real-switch introduction phases:

- Fake-driver unit tests for real-switch helper API behavior.
- Default no-op tests (feature disabled / mode off / non-allowed operation).
- Context index mapping tests (selected index -> internal raw name mapping correctness).
- Raw context name non-leakage tests across metadata/reporting/exception paths.
- Switch failure tests.
- Restore failure tests.
- Operation failure tests after successful switch.
- Validate/extract result contract tests under safety failures.
- Execute-unwired tests (explicit regression guard).
- JSON/HTML report tests for metadata shape/sanitization continuity.
- Android real-env smoke (later phase).
- iOS real-env smoke (later phase).

## 11. Sample app / real-env readiness

Before enabling real-switch smoke in real environments, readiness requires:

- Android hybrid/WebView sample app (or known deterministic screen).
- iOS hybrid/WebView sample app (or known deterministic screen).
- Stable and repeatable WebView context exposure behavior.
- Known WebView target where validate/extract expectations are deterministic.
- Ability to run and capture diagnostics without credentials/secrets leakage in logs/reports.

## 12. Risk matrix

| Risk | Impact | Mitigation |
|---|---|---|
| Wrong WebView context selected | Incorrect operation target, false results | Deterministic selection policy + index mapping tests + fail-closed rules |
| Context list changes between collect and switch | Stale index/name mapping | Mandatory inventory refresh before switch + stale-context failure handling |
| Restore failure | Session left in wrong context | Restore mandatory + failure overrides success + immediate halt |
| WebView target not loaded | Validate/extract instability | Readiness checks + explicit `webview_not_ready` failure class |
| Native dialog interrupts flow | Switch/operation blocked or redirected | System dialog guardrail gate + blocked/deferred outcome |
| Cloud provider context variance | Inconsistent behavior across vendors | Defer to later cloud smoke phase + provider-specific diagnostics |
| iOS context variance | Context name/type differences | iOS-specific smoke criteria and variance tests |
| Accidental execute wiring | Broader blast radius | Explicit execute-unwired tests + phase-scoped gate checks |
| Raw context leakage | Security/privacy reporting regression | Strict sanitization + leakage regression tests |

## 13. Proposed implementation sequence

Recommended sequence after this design review:

1. **20X — Real Driver Switch Helper Skeleton, not wired**
2. **20Y — Real Driver Switch Helper Unit Tests with fake driver object**
3. **20Z — Strict Opt-in Validate/Extract Real Switching MVP**
4. **21A — Android WebView Real-Env Smoke**
5. **21B — iOS WebView Real-Env Smoke**
6. **21C — Cloud WebView Smoke Trial**

## 14. GO/NO-GO recommendation

**Recommendation: GO for 20X only** if all of the following remain true:

- Helper remains isolated (no adapter runtime wiring yet).
- No runtime adapter path uses real context switch yet.
- Raw context names remain internal-only.
- Restore behavior is fail-closed on restore failure.
- Scope remains validate/extract-only for MVP planning.

If any condition is violated, recommendation is **NO-GO** until corrected.
