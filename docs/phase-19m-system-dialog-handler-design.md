# Phase 19M-T — SystemDialogHandler Design (Design-Only)

## 1) Problem statement

System dialogs are a high-impact interruption surface in mobile automation and must be treated differently from normal app UI:

- permission dialogs can interrupt otherwise deterministic flows and block subsequent target resolution;
- dialog overlays can hide or replace app-owned elements, causing object identification failures or false ambiguities;
- Android and iOS render dialogs with different hierarchy shapes, labels, and ownership signals;
- platform-owned UI can appear outside normal app-owned hierarchy expectations;
- blind clicking is unsafe and can trigger destructive, privacy-sensitive, or policy-violating outcomes.

A future SystemDialogHandler is therefore needed to safely **detect, classify, and report** dialog state first, with any future handling gated by explicit policy and opt-in.

## 2) Scope

This phase is **design only** for a future `SystemDialogHandler`:

- detection strategy for likely system-dialog presence;
- classification strategy for dialog type/platform/ownership;
- safe metadata schema for diagnostics;
- reporting and analytics strategy;
- future handling policy design (without implementation).

## 3) Non-goals

This phase does **not** implement or change runtime behavior:

- no runtime dialog handling implementation;
- no automatic clicking;
- no Appium adapter behavior changes;
- no WebView switching logic;
- no resolver routing/priority/order changes;
- no ranker/scoring/confidence model changes for object selection;
- no public API/schema changes;
- no dependency changes;
- no package version change;
- no benchmark default behavior change.

## 4) Dialog categories

Future classification taxonomy should include at minimum:

- `android_permission_dialog`
- `ios_permission_dialog`
- `confirm_cancel_dialog` (generic OK/Cancel)
- `allow_deny_dialog`
- `system_alert`
- `app_modal` (app-owned modal surface)
- `unknown_dialog_surface`

For compact metadata, categories can map to normalized public-safe types:

- `permission`
- `confirm_cancel`
- `alert`
- `unknown`

while preserving richer internal evidence tokens.

## 5) Detection signals (safe only)

The detector should use additive, sanitized signals (no raw dump persistence):

1. **Hierarchy XML token presence**
   - permission/action phrase tokens (normalized and lowercased);
   - dialog-related class/type hints;
   - structural hints indicating alert-style container.

2. **Platform/capability hints**
   - normalized platform (`android|ios|unknown`);
   - automation family hints (`uiautomator2|xcuitest|unknown`).

3. **FrameworkDetector bridge signal**
   - consume `framework_detection.surface_type == system_dialog` as strong upstream evidence.

4. **Text token set (sanitized)**
   - examples: `allow`, `deny`, `while using`, `only this time`, `don't allow`, `ok`, `cancel`.

5. **Class/type hints**
   - Android widget/type indicators commonly seen in UiAutomator2 snapshots;
   - iOS `XCUIElementTypeAlert` and related alert/action elements.

6. **Package/bundle ownership hints (sanitized)**
   - reduce to ownership class tokens (e.g., `owner:system_pkg_hint`) instead of storing full package/bundle values.

7. **Current context metadata**
   - use `context_inventory` and framework metadata to support ambiguity reduction, not context switching.

## 6) Proposed SystemDialogHandler output schema

Proposed internal-safe metadata object (design target):

```json
{
  "dialog_detected": true,
  "dialog_type": "permission|confirm_cancel|alert|unknown",
  "platform": "android|ios|unknown",
  "owner": "system|app|unknown",
  "recommended_action": "allow|deny|dismiss|defer|manual_review|unknown",
  "confidence": 0.0,
  "evidence": ["surface:system_dialog", "token:allow", "platform:android"],
  "warnings": [],
  "safe_metadata_only": true
}
```

Notes:
- `confidence` is **dialog classification confidence only**, not target ranking confidence.
- `evidence` must be compact tokens only (no raw XML, raw screenshots, raw context names, full package names).
- `safe_metadata_only` remains true by default.

## 7) Recommended action policy (future-facing)

Default posture: **detect/report only**.

Recommended action meanings:

- `allow`: candidate positive permission action (future opt-in only).
- `deny`: candidate negative permission action (future opt-in only).
- `ok`: map to `dismiss` or confirm path only under explicit policy.
- `cancel`: map to `dismiss` only under explicit policy.
- `dismiss`: non-destructive close intent when safely identifiable.
- `manual_review`: require human decision when policy/risk is unclear.
- `defer`: abstain during current step and emit diagnostics.
- `unknown`: insufficient confidence/ambiguity.

Policy rule: future auto-action must require explicit opt-in and explicit allowlist policy.

## 8) Safety guardrails

Future handler guardrails should be fail-closed:

- never auto-click by default;
- explicit opt-in required for any future auto-handling mode;
- never click destructive/deny/confirm actions without explicit policy mapping;
- no handling if confidence is below threshold;
- no handling when multiple candidate buttons match action intent;
- fail closed on ambiguity/conflict;
- always emit safe diagnostics even when abstaining.

## 9) Android-specific design

Detection/classification heuristics for Android (UiAutomator2-focused):

- hierarchy patterns often expose `android.widget.*` classes with resource/content attributes;
- common permission-action labels include:
  - `Allow`
  - `Allow while using app`
  - `Only this time`
  - `Don't allow`
- permission dialog variants differ across Android 12/13/14 and OEM overlays;
- resource-id/class hints can support confidence when sanitized into tokenized evidence;
- package/system hints should be reduced to ownership signals (e.g., `owner:system`) rather than raw identifiers.

Design principle: classification should tolerate label drift and rely on combined evidence, not one exact string.

## 10) iOS-specific design

Detection/classification heuristics for iOS (XCUITest-focused):

- alert surfaces frequently map to `XCUIElementTypeAlert`;
- action labels may appear through `label`, `name`, and sometimes `value` combinations;
- common permission/alert actions include:
  - `Allow`
  - `Don't Allow`
  - `OK`
- iOS system alert rendering can differ by OS version and permission family.

Design principle: use multi-field tokenization (`label/name/value`) and preserve only normalized evidence tokens.

## 11) App-owned modal vs system dialog distinction

Avoiding misclassification is critical.

Suggested ownership decision stack:

1. prefer explicit system ownership hints (sanitized package/bundle class token, known system alert type);
2. require permission/action token co-occurrence before elevating to `system` ownership when ownership hints are weak;
3. if app-specific branding/layout and no system hints are present, classify as `app` modal;
4. when conflicting/missing ownership evidence persists, classify `owner=unknown`, `dialog_type=unknown`, and `recommended_action=manual_review|defer`.

## 12) Future integration points

Future implementation should integrate metadata-only output at existing safe seams:

- `FrameworkDetector` output consumption (`surface_type` signals);
- `AppiumAdapter.collect_context` app-state enrichment (metadata only);
- `AppiumHierarchyResolver` diagnostics enrichment (no ranking/routing changes);
- `StepResult.target.metadata` safe inclusion;
- JSON/HTML reporting summaries;
- real-env Android/iOS smoke assertions;
- benchmark seed diagnostics views.

## 13) Reporting/analytics design

Proposed safe analytics fields (future):

- `system_dialog_summary`
- `dialog_type_counts`
- `recommended_action_counts`
- `confidence_buckets` (e.g., `0-0.39`, `0.40-0.69`, `0.70-1.00`)
- `warnings`
- `dialog_detected_count`
- `dialog_not_detected_count`

All analytics must remain sanitized, aggregate-friendly, and free of raw hierarchy payloads.

## 14) Benchmark impact

Current object-intelligence benchmark seeds already cover dialog-adjacent intent patterns, including permission allow/deny and OK/Cancel style actions. This is sufficient for initial metadata-only detector MVP validation.

Recommendation:

- keep existing benchmark default behavior unchanged;
- add **optional** future seeds only if needed for:
  - iOS-specific phrasing variants,
  - localization variants,
  - ambiguous app-modal vs system-dialog negative controls.

## 15) Future implementation plan (safe sub-phases)

Recommended rollout after this design:

1. **Metadata-only detector helper MVP**
   - standalone classifier function returning safe schema only.
2. **Reporting/analytics support**
   - aggregate counts and warnings in JSON/HTML reports.
3. **Android emulator detection smoke**
   - detection assertions only; no clicking policy execution.
4. **iOS simulator detection smoke**
   - parity detection assertions only.
5. **Opt-in handler guardrails**
   - policy gates for any future action-capable mode.
6. **Optional explicit auto-action MVP**
   - only with strict opt-in, single-match constraints, and high-confidence policy checks.

## 16) Test strategy (future)

Planned test coverage:

- Android permission dialog detection;
- iOS permission dialog detection;
- generic OK/Cancel detection;
- app modal not misclassified as system dialog;
- ambiguous dialog fails closed;
- evidence remains sanitized;
- no raw XML/context/package leakage in diagnostics;
- no auto-click by default;
- explicit opt-in required for any future auto-action path.

## 17) Risks and mitigations

- **False-positive system-dialog detection**
  - mitigate via multi-signal thresholding and owner unknown fallback.
- **Destructive click risk**
  - mitigate with detect-only default, explicit opt-in, and deny/confirm policy gating.
- **OS label variation**
  - mitigate via token families and synonym sets, not strict string equality.
- **Localization differences**
  - mitigate with extensible token dictionaries and unknown/defer fallback.
- **Device/version variance**
  - mitigate with emulator/simulator + real-device smoke matrices.
- **App-modal confusion**
  - mitigate with ownership-first rules and fail-closed ambiguity policy.
- **Flaky hierarchy timing**
  - mitigate with retryable metadata sampling and deterministic abstain behavior.

## 18) Recommended next phase

**Recommended: Phase 19M-U — SystemDialogHandler Metadata-Only Detector MVP.**

Rationale:

- directly follows this design with lowest runtime risk;
- preserves current no-click, no-switching safety constraints;
- enables measurable reporting value quickly;
- creates foundation needed before any future opt-in handling discussion.

## GO / NO-GO

**GO** for Phase 19M-U Metadata-Only Detector MVP under strict detect/report-only policy.
