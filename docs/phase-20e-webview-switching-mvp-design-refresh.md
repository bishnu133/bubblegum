# Phase 20E — WebView Switching MVP Design Refresh (Design-Only)

## 1) Purpose

WebView switching should be refreshed at design level before implementation because Bubblegum now has a stronger safety baseline than earlier 19M design snapshots: structured context inventory, framework detection, dry-run switch diagnostics, guardrails, reporting redaction, and real-environment smoke harnesses across Android/iOS/cloud. The implementation plan should therefore be updated to explicitly use these guardrails and to preserve deterministic fail-closed behavior.

This phase aligns future WebView switching with the current state of the project and prevents unsafe or premature runtime changes in Appium adapter behavior.

## 2) Current foundation

The following pieces are already implemented and available as prerequisites for a safe MVP:

- **`context_inventory`** metadata in mobile app-state, including safe context type/count summaries and inferred mode.
- **`framework_detection`** metadata for surface classification (`android_native`, `ios_native`, `webview`, `hybrid`, `system_dialog`, `unknown`) and confidence/evidence/warnings.
- **`webview_switch_diagnostics`** dry-run diagnostics that classify candidacy (`webview_candidate`, `hybrid_candidate`, etc.) without performing a context switch.
- **`webview_switch_guardrails`** policy output (`allowed`, `blocked`, `deferred`, `unsupported`) using explicit opt-in and safe metadata-only evidence.
- **WebView reporting/analytics hooks** in JSON/HTML report builders with redaction-focused safe-field extraction.
- **Android/iOS/cloud real-env smoke harnesses** (skip-by-default, opt-in) providing a safe validation path for later WebView switch smoke coverage.
- **System dialog guardrails** already tracked as dedicated metadata to avoid surface confusion and unsafe cross-context behavior.
- **Scroll, repeated-region, icon, and mobile memory signature metadata tracks** that improve context-aware diagnostics while preserving non-switching runtime behavior.

## 3) Non-goals

This phase is strictly design refresh and does **not** change runtime behavior.

- No WebView switching implementation.
- No `driver.switch_to.context` usage.
- No default automatic switching.
- No resolver routing/priority/order changes.
- No ranker/scoring/confidence changes.
- No cloud execution behavior changes.

## 4) MVP switching policy

For the first implementation MVP, enforce the following safety policy:

1. **Explicit opt-in required** (default remains off).
2. **Mobile channel only** (Appium mobile flows).
3. **Only WebView/hybrid candidate surfaces** are eligible.
4. **Dry-run diagnostics must be candidate-positive** (`webview_candidate` or `hybrid_candidate`).
5. **Guardrails must allow** switching before any attempt.
6. **Original context must be captured** before attempting switch logic.
7. **Context must be restored** after action/validation regardless of outcome.
8. **Fail closed** on ambiguity, missing prerequisites, or any switching/restore error.

## 5) Eligibility rules

Switching may be allowed only when all of the following conditions hold:

- Surface/diagnostics indicate `webview_candidate` or `hybrid_candidate`.
- At least one WebView context is available in `context_inventory`.
- Either exactly one WebView exists, or an explicit multi-WebView selection strategy is configured.
- No active system dialog surface is present.
- No unresolved app modal blocker is active.
- Instruction semantics include a web-like target/action hint.
- Effective run configuration enables WebView switching mode for this step.

## 6) Block/defer rules

Switching must be blocked or deferred in these cases:

- Explicit opt-in missing.
- Surface is native-only.
- Surface is system-dialog.
- Surface is unknown.
- Multiple WebViews exist and no selection policy is configured.
- WebView context is missing.
- Target/action hint is too weak for web intent.
- Context inventory is unavailable/incomplete.
- Switch or restore appears high risk (non-deterministic or unstable signals).

Suggested handling:
- **Blocked** for hard policy disallow.
- **Deferred** for temporary ambiguity that might be resolved later in run.
- **Unsupported** where capability constraints prevent safe execution.

## 7) Proposed config flags

Design-only proposed configuration shape for future phases:

- `enable_webview_switching: bool`  
  Master feature gate (default `false`).

- `webview_switching_mode: "off" | "dry_run" | "opt_in"`  
  - `off`: fully disabled.  
  - `dry_run`: metadata-only diagnostics/guardrails; no runtime switch.  
  - `opt_in`: eligible steps may perform guarded switch/restore.

- `max_webview_switch_attempts: int`  
  Bounded retry/attempt ceiling per step.

- `require_restore_context: bool`  
  Require restore attempt and status tracking.

- `allow_multi_webview_selection: bool`  
  Controls whether >1 WebView can be considered.

- `webview_context_selection_policy: str`  
  Declarative selection strategy identifier (for example deterministic-first-safe-match).

- `fail_closed_on_restore_failure: bool`  
  If restore fails, mark step as failed/deferred per policy and avoid continued unsafe execution.

## 8) Proposed internal API

Design-only helper boundaries for future implementation:

- `evaluate_webview_switch_eligibility(...)`  
  Consumes diagnostics + guardrails + instruction hints + config and returns allow/block/defer decision with reasons.

- `select_webview_context(...)`  
  Selects target WebView context using configured strategy and returns safe metadata-only rationale.

- `execute_with_webview_context(...)`  
  Orchestrates capture-original, guarded switch, action/validation callback, and cleanup handling.

- `restore_original_context(...)`  
  Performs deterministic restoration and returns restore status/warnings.

- `build_webview_switch_result_metadata(...)`  
  Builds sanitized metadata payload for reports/analytics without raw context names.

> Note: This section is design only; no runtime code changes in Phase 20E.

## 9) Metadata schema

Future runtime metadata should remain safe/sanitized and include:

- `switch_enabled`
- `switch_attempted`
- `switch_status`
- `original_context_type`
- `selected_context_type`
- `context_selection_reason`
- `restore_attempted`
- `restore_status`
- `reason`
- `evidence`
- `warnings`
- `safe_metadata_only`

Safety requirement: **do not include raw context names** (for example `WEBVIEW_com.example`). Emit only normalized/safe types and tokenized reason labels.

## 10) Reporting/analytics plan

Add future report visibility under:

- JSON/HTML section title: **WebView Switch Execution**
- Analytics key: **`webview_switch_execution_summary`**

Proposed counters:

- `total_with_switch_metadata`
- `switch_attempted_count`
- `switch_success_count`
- `switch_failed_count`
- `restore_success_count`
- `restore_failed_count`
- `reason_counts`
- `warning_counts`

Reporting must stay sanitization-first and preserve existing no-raw-payload guarantees.

## 11) Test strategy

Future implementation phases should include:

- Unit tests for eligibility evaluator decisions.
- Unit tests for context selection policy behavior.
- Unit tests for restore behavior with fake/mock driver.
- Unit tests for error/failure-path handling (switch fail, stale context, restore fail).
- JSON/HTML report sanitization tests for new metadata fields.
- Android real-env opt-in WebView switch smoke.
- iOS real-env opt-in WebView switch smoke.
- Cloud opt-in smoke in later phase after local/mobile confidence.

## 12) Risk assessment

Primary risks and mitigation direction:

- **Wrong WebView selected**  
  Mitigate with deterministic selection policy + explicit block/defer on ambiguity.

- **Restore failure**  
  Mitigate with mandatory restore attempts, explicit restore status, and fail-closed policy.

- **Native action attempted in WebView**  
  Mitigate via eligibility checks requiring web-like intent hints and surface consistency.

- **WebView action attempted in native context**  
  Mitigate with diagnostics-positive gating and context availability checks.

- **System dialog interruption**  
  Mitigate by blocking switching when system-dialog guardrails are active.

- **Provider/cloud context variance**  
  Mitigate with opt-in staged rollout and deferred cloud execution validation.

- **Hybrid app flakiness**  
  Mitigate with bounded attempts, strong metadata observability, and fail-closed semantics.

## 13) Implementation sequence recommendation

Recommended phased rollout after this refresh:

1. **Phase 20F — WebView Switching Eligibility Evaluator MVP**
2. **Phase 20G — WebView Context Selection Helper**
3. **Phase 20H — WebView Switching Opt-in Execution MVP**
4. **Phase 20I — WebView Switch Reporting/Analytics**
5. **Phase 20J — Android/iOS Real-Env WebView Switch Smoke**

## 14) GO/NO-GO

Recommendation: **GO for Phase 20F only**, contingent on this safety model being accepted:

- explicit opt-in default-off,
- fail-closed decisions,
- deterministic eligibility and context-selection prerequisites,
- guaranteed restore-path design,
- metadata-only safe reporting contract.

If any of the above constraints are relaxed, recommendation becomes **NO-GO** until safety constraints are reinstated.
