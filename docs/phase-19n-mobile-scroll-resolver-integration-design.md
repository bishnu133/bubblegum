# Phase 19N-F — Mobile Scroll Resolver Integration Design

## 1) Problem statement

Bubblegum already has mobile scroll/off-screen discovery primitives, but normal resolver and action flows still operate against the *currently visible* hierarchy snapshot only.

This creates a practical gap for common mobile UI patterns:
- Targets may not exist in the current visible hierarchy window.
- Long lists frequently place desired items off-screen.
- Important actions (for example, below-the-fold buttons) may not be directly discoverable without scrolling.
- The current resolver cannot match elements that are not yet visible.

At the same time, uncontrolled runtime scrolling can introduce significant flakiness:
- Non-deterministic screen positions.
- Unbounded retry loops.
- Interference from modals/system dialogs/keyboards.
- Increased latency and unstable action outcomes.

The design goal is to define a **safe, bounded, opt-in integration path** for future runtime use, while preserving current deterministic behavior by default.

## 2) Current foundation

Phase 19N-C/D/E established key building blocks that reduce implementation risk:

- `build_mobile_scroll_discovery_plan(...)` exists for pre-execution discovery planning.
- `execute_bounded_mobile_scroll_search(...)` exists for bounded scroll search execution.
- `UIContext.app_state["scroll_discovery"]` stores discovery output/state.
- Scroll Discovery reporting/analytics is already present.
- Android real-environment scroll smoke coverage exists (opt-in / skip-by-default).

These foundations support adding integration logic later without changing ranking or resolver fundamentals in this phase.

## 3) Scope (Design only)

This phase defines architecture and policy only:
- Integration points for future runtime hook-in.
- Safety guardrails and stop conditions.
- Resolver/action flow options and trade-offs.
- Metadata and analytics extension plan.
- Testing strategy for a future MVP.

No runtime integration is implemented in this phase.

## 4) Non-goals

This phase explicitly does **not** include:
- Runtime implementation of auto-scroll.
- Wiring scroll execution into normal `act`/`verify`/`extract` flows.
- Resolver routing/priority/order changes.
- Ranker/scoring/confidence changes.
- Appium adapter action behavior changes.
- iOS or cloud execution support.
- WebView context switching.
- Any `driver.switch_to.context` usage.
- Package version changes.
- Dependency changes.

## 5) Integration options

### Option A — Resolver emits `scroll_required` metadata only

**Description**
- Keep resolver behavior unchanged.
- When no confident visible match exists, emit metadata indicating likely off-screen target (`scroll_needed=true`, reason/hints).
- No runtime scrolling is performed.

**Pros**
- Safest and lowest-risk behavior.
- No runtime flakiness introduced.
- Preserves deterministic execution and current test baselines.
- Enables UX/policy experimentation with zero action-layer changes.

**Cons**
- Cannot recover automatically from off-screen misses.
- User or higher-level orchestration must initiate scrolling.

**Risk**
- Low technical risk, medium product effectiveness risk (still no automatic recovery).

**Recommended fit**
- Excellent transitional baseline and default posture.

---

### Option B — Action layer performs bounded scroll retry after no-match

**Description**
- Keep resolver unchanged initially.
- After no-match in action flow, action layer conditionally executes bounded scroll attempts.
- After each scroll, re-collect hierarchy and re-run existing resolver.

**Pros**
- Minimal resolver architecture disruption.
- Clear control point for safety policy and opt-in gating.
- Easy to keep existing ranking and matching logic untouched.

**Cons**
- Action layer takes on extra orchestration complexity.
- Cross-cutting concerns (dialog detection, keyboard/modal checks) grow in action code.
- May be harder to generalize across act/verify/extract later.

**Risk**
- Medium flakiness risk if gating/guardrails are incomplete.

**Recommended fit**
- Strong candidate for first runtime MVP when combined with strict safeguards.

---

### Option C — New `MobileScrollResolver` runs after `AppiumHierarchyResolver`

**Description**
- Introduce a dedicated resolver stage that executes bounded scroll search when base resolver yields no match and policy allows.
- Integrates scroll awareness inside resolver stack while preserving existing ranker.

**Pros**
- Cleaner long-term separation of concerns.
- Easier reuse for act/verify/extract through common resolver pipeline.
- Centralizes scroll-specific metadata and decisioning.

**Cons**
- Higher architecture and testing complexity than Option B.
- Risks accidental routing/order regressions if not carefully isolated.
- More intrusive to resolver pipeline evolution.

**Risk**
- Medium/high integration risk for early MVP.

**Recommended fit**
- Better as a second step after initial bounded policy proves stable.

---

### Option D — Explicit user step only (e.g., “scroll until Settings is visible”)

**Description**
- Scroll remains a deliberate high-level instruction.
- System executes bounded scrolling only for explicit scroll directives.

**Pros**
- High transparency and user control.
- Lower surprise and easier debugging.
- Avoids hidden automatic behavior.

**Cons**
- More burden on prompt/task author.
- Lower autonomy and weaker out-of-box success for generic intents.

**Risk**
- Low technical risk, medium usability risk.

**Recommended fit**
- Good fallback/control mode; useful alongside Option A and as safety override.

## 6) Recommended MVP policy

Recommended safest MVP path:
- Default: **no automatic scroll**.
- Allow bounded runtime scroll resolution only when all gating conditions pass:
  - Channel is mobile.
  - `scroll_discovery.status == "candidate"`.
  - `scroll_needed == true`.
  - Explicit integration flag/option is enabled (opt-in).
  - Target hint is sufficiently clear (e.g., stable text/accessibility id/class hint).
  - `max_scrolls` is configured and bounded.
  - No system dialog is active.
  - No WebView/native context switch is required.

Execution policy (future phase):
1. Attempt normal resolver first.
2. If no match and policy gate passes, perform one bounded scroll step.
3. Re-collect hierarchy snapshot.
4. Re-run normal resolver unchanged.
5. Stop immediately when target is found.
6. Stop/fail safely when attempts exhausted or safety block appears.

This keeps existing resolver scoring semantics intact while adding controlled recovery only for qualified off-screen cases.

## 7) Safety guardrails

Required guardrails for future implementation:
- Hard `max_scrolls` cap (no unbounded retries).
- No infinite loops; attempt counter must strictly increase.
- No raw XML/screenshot leakage in logs/metadata.
- Block scrolling when a system dialog is active.
- Block scrolling when keyboard/modal obstructs screen unless explicitly allowed by policy.
- Never scroll across WebView/native context boundary.
- Never perform destructive actions after scroll unless target is re-resolved and re-verified in current snapshot.
- Prefer no-op/early-fail over speculative movement when safety signals are ambiguous.

## 8) Metadata design

Proposed future safe metadata (names illustrative):

```yaml
scroll_resolution:
  enabled: bool
  attempted: bool
  attempt_count: int
  max_scrolls: int
  found_after_scroll: bool
  final_status: one_of[not_enabled, skipped, blocked, found, exhausted, error]
  reason: short_machine_reason
  evidence:
    target_hint_type: optional
    target_hint_value_redacted: optional
    discovery_status: optional
  warnings: [string]
  safe_metadata_only: true
```

Notes:
- Keep metadata strictly non-sensitive.
- Redact or omit raw hierarchy and screenshot payloads.
- Preserve enough structured fields for observability and triage.

## 9) Reporting/analytics design

Proposed future analytics counters:
- `total_scroll_resolution_attempts`
- `found_after_scroll_count`
- `exhausted_count`
- `blocked_by_dialog_count`
- `max_scrolls_bucket` (e.g., 0/1/2/3/4+)
- `warning_counts` by warning type

Analytics should remain aggregate-safe and should not include raw UI artifacts.

## 10) Test strategy (future MVP)

Planned validation coverage:
- Unit tests with fake driver and deterministic hierarchy fixtures.
- Assert no-scroll behavior when opt-in flag is false.
- Assert bounded attempts never exceed configured `max_scrolls`.
- Assert resolver is re-run after each scroll step.
- Assert flow stops immediately after target is found.
- Assert safe failure after max attempts exhausted.
- Assert no-scroll when system dialog is detected.
- Assert no raw XML/screenshot leakage in metadata/reporting.
- Android real-environment opt-in smoke test for bounded happy path.
- Benchmark seed validation to ensure collect-only baseline integrity.

## 11) Risks and mitigations

- **Flaky scroll behavior**
  - Mitigation: strict bounds, deterministic scroll step policy, conservative default-off.
- **Dynamic/infinite list loading variance**
  - Mitigation: attempt cap + explicit `exhausted` outcome + non-fatal fail semantics.
- **Duplicate targets after scroll**
  - Mitigation: reuse existing resolver ranking; require post-scroll re-verification.
- **Keyboard/modal obstruction**
  - Mitigation: pre-scroll blockers and explicit allowlist policy.
- **App-specific gesture differences**
  - Mitigation: adapter strategy abstraction; narrow Android MVP first.
- **Target appears then disappears**
  - Mitigation: resolve-and-act immediately with fresh snapshot checks.
- **Performance overhead**
  - Mitigation: opt-in gating, low default bounds, analytics-driven tuning.

## 12) Recommended next phase

Recommend:

**Phase 19N-G — Mobile Scroll Resolver Integration MVP**

Suggested implementation order for 19N-G:
1. Start with Option B (action-layer bounded retry), guarded behind explicit opt-in.
2. Keep resolver ranking/order unchanged.
3. Enforce guardrails and safe metadata.
4. Validate with unit tests + Android opt-in real-env smoke.
5. Reassess for potential migration toward Option C after stability evidence.

---

## Validation expectations for this phase

For this design-only phase, expected checks remain:
- `pytest --collect-only -q` should remain at established baseline (786 collected).
- `git diff --check` should show no whitespace/conflict issues.
- Runtime behavior should remain unchanged.
