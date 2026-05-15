# Phase 19M-Z — Android System Dialog Safe Action Design (MVP)

## Status
Design-only proposal. No runtime behavior changes are included in this phase.

## 1) Problem Statement

Phases 19M-U, 19M-X, and 19M-Y established:
- detection of potential system dialogs,
- guardrail decisions about whether action is allowed,
- and reporting/analytics around those decisions.

A real-world issue was observed on Android where a system permission **Allow** button visually overlapped with an app popup behind it. This creates a high-risk ambiguity: text matching alone can select an element that appears to be the intended control but is actually in a different UI layer.

This phase defines a safe-action design for a future MVP that can act on system dialog buttons only when explicit opt-in and strict guardrails are satisfied.

## 2) Why Text-Only Clicking Is Unsafe

Text-only matching (e.g., selecting any visible element with text like "Allow", "Deny", or "OK") is unsafe because:
- The same labels are frequently reused in app-owned dialogs/popups.
- Multiple matching candidates can exist simultaneously.
- Overlapping UI layers can place an app element beneath or near a system element.
- Localization and OEM variations can alter text meaning/context.
- Accessibility text can be present for off-target elements.

Therefore, text is only one weak signal and cannot be the sole basis for safe automated action.

## 3) Scope and Non-Goals

### In Scope (Design)
- Define preconditions and guardrails for a future Android-safe-action MVP.
- Define candidate-selection logic constraints.
- Define overlap/occlusion rejection behavior.
- Define reporting expectations and rollout sequence.

### Non-Goals (This Phase)
- No clicking implementation.
- No accept/deny/dismiss execution logic.
- No changes to Appium action behavior.
- No changes to resolver/ranker/scoring behavior.
- No new dependencies.
- No context switching (`driver.switch_to.context`) usage.

## 4) Required Preconditions

A future action path must be gated by **all** of the following:

1. `system_dialog_detection.dialog_detected == true`
2. `system_dialog_guardrails.decision == allowed`
3. Explicit opt-in is enabled (default off).
4. Candidate confidence is at or above a configured threshold.
5. Exactly one safe candidate remains after filtering.

If any precondition fails, default to no action and record deferred/manual-review reason metadata.

## 5) Candidate Selection Rules

For future resolver-only selection helper logic:

1. **Prefer system-owned dialog candidates**
   - Prioritize candidates attributable to Android/system dialog container lineage.
   - De-prioritize app package ownership when system ownership is expected.

2. **Prefer stable structural hints over label text**
   - Resource-id patterns, class/type signatures, and known dialog container ancestry should outweigh plain text.
   - Text acts as supporting evidence only.

3. **Restrict to active/topmost dialog region**
   - Candidate bounds must lie within the active dialog container bounds (or a conservative inner region).

4. **Require interactability flags**
   - Candidate must be visible, enabled, and clickable according to available element attributes.

5. **Reject likely background/app popup candidates**
   - Exclude candidates tied to non-active layers or app-owned popup regions outside active system dialog bounds.

## 6) Overlap/Occlusion Handling

To address the observed overlap issue:

1. Compare candidate bounds against detected dialog bounds.
2. Reject candidates outside the active dialog container.
3. If ownership/topmost layer is ambiguous, **defer** (no action).
4. If multiple similarly valid candidates remain after occlusion checks, **defer**.

Conservative failure (no action) is preferred over risky mis-clicks.

## 7) Allowed Future Actions

If and only if all preconditions and filters pass, future MVP may map safe intent categories to one of:
- `allow`
- `deny`
- `ok`
- `cancel`
- `dismiss`

No other action categories are in scope for MVP.

## 8) Default Behavior

Default remains:
- **No action** unless all strict gates are satisfied.
- On ambiguity or incomplete evidence, return `manual_review` / `deferred` outcome with reason metadata.

## 9) Safety and Privacy Constraints

Reporting and telemetry for this capability must not leak sensitive artifacts. Specifically, no raw:
- XML/DOM dumps,
- screenshots,
- context identifiers,
- package identifiers.

Only minimal, structured, non-sensitive metadata should be emitted.

## 10) Future Implementation Phases

Recommended sequence:

1. **Resolver-only candidate selection helper**
   - Introduce deterministic filtering/ranking helper for safe candidates.
   - No click path yet.

2. **Fake-driver unit tests**
   - Validate gating, candidate rejection, overlap/ambiguity behavior.

3. **Android emulator opt-in smoke**
   - Run opt-in-only integration scenarios for representative permission/system dialogs.

4. **Report metadata expansion**
   - Add non-sensitive reason codes and decision metadata for observability.

5. **Real action MVP**
   - Enable actual tap/action only after prior phases pass acceptance criteria.

## 11) Test Strategy

### Design-Phase Validation (Current)
- Docs-only change.
- Repository checks:
  - `pytest --collect-only -q`
  - `git diff --check`

### Future Implementation Validation
- Unit tests for each precondition gate.
- Unit tests for overlap/occlusion rejection.
- Negative tests for duplicate labels across layers.
- Localization variance tests where text differs but structural signals remain stable.
- Opt-in gating tests (off by default).
- Regression tests proving no changes to unrelated Appium action flows.

## 12) GO/NO-GO Recommendation for MVP Implementation

**Recommendation: Conditional GO (for implementation planning), with strict launch gates.**

Proceed to implementation only if:
- The resolver-only helper demonstrates deterministic, conservative selection.
- Unit and fake-driver tests show low false-positive risk in overlap scenarios.
- Opt-in emulator smoke runs are stable across representative Android versions/OEM skins.
- Privacy constraints are upheld in reporting.

If any gate is unmet, **NO-GO** and keep default behavior as no action/deferred.

---

## Explicit Phase Outcome

Phase 19M-Z delivers design documentation only.
- No runtime behavior changed.
- No click behavior added.
- No resolver/ranker/scoring behavior changed.
