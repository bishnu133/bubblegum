# Phase 19M-D — WebView Context Switching Design (Design-Only)

## 1) Problem statement

Bubblegum mobile object intelligence currently resolves targets from the active Appium hierarchy snapshot (`driver.page_source`) and does not model or switch Appium contexts (`NATIVE_APP`, `WEBVIEW_*`). In hybrid apps, actionable elements may exist in an embedded WebView while the active context remains native; this can make native-only hierarchy matching miss valid targets or produce ambiguity when a web surface is present but not inspected.

A deterministic context model is needed so future phases can:
- determine whether native, webview, or mixed surfaces are present,
- decide when context switching is worth attempting,
- preserve safe fallbacks to native behavior,
- expose auditable diagnostics without leaking raw UI payloads.

## 2) Scope

This phase is **design only** and defines future behavior for:
- context inventory and classification inputs,
- future context switching decision rules,
- resolver routing design across native/webview/hybrid,
- safe metadata/reporting fields for diagnostics,
- memory/signature separation strategy by surface/context.

No runtime implementation occurs in this phase.

## 3) Non-goals

- No WebView switching implementation in runtime code.
- No Appium adapter behavior changes in this phase.
- No resolver priority/order changes.
- No ranker/scoring/confidence changes.
- No browser/Chromedriver dependency changes.
- No public API/schema changes.
- No default benchmark behavior changes.

## 4) Current capability summary

### Appium adapter today
Current collection is native-hierarchy oriented:
- captures hierarchy XML from `driver.page_source` when hierarchy/accessibility is requested,
- optionally captures screenshot bytes,
- computes `screen_signature` from activity + hierarchy XML,
- does not expose an explicit context inventory model (`available_contexts`, selected context, switch outcome).

### AppiumHierarchyResolver today
Current mobile Tier-1 resolver:
- parses one hierarchy XML tree,
- matches mainly `text`, `content-desc`, `resource-id`,
- emits candidates with existing confidence tiers,
- supports missing hierarchy safely by returning no candidates,
- does not route across multiple Appium contexts.

### Seed fixture coverage after Phase 19M-C
Object intelligence seed inventory now includes mobile-relevant WebView/hybrid/system-dialog-style cases at benchmark level (plus Android/iOS native patterns, icon-only, scroll/off-screen, repeated cards, relational targets), improving design validation coverage for future phases.

### What is missing for hybrid apps
- standardized context inventory metadata,
- deterministic selection between native and webview surfaces,
- safe, reversible switch policy,
- cross-surface candidate arbitration rules,
- context-aware memory signature partitioning.

## 5) Proposed WebView context model (future internal metadata)

Future internal metadata shape (illustrative, non-binding):

```json
{
  "available_contexts": ["NATIVE_APP", "WEBVIEW_com.example"],
  "current_context": "NATIVE_APP",
  "native_context": "NATIVE_APP",
  "webview_contexts": ["WEBVIEW_com.example"],
  "selected_context": "NATIVE_APP",
  "context_switch_attempted": false,
  "context_switch_result": "not_attempted",
  "fallback_to_native": false
}
```

Semantics:
- `available_contexts`: compact sanitized list (no verbose internals).
- `current_context`: driver-reported active context at capture start.
- `native_context`: canonical native context identifier (usually `NATIVE_APP`).
- `webview_contexts`: detected `WEBVIEW_*` context names.
- `selected_context`: context chosen by future routing logic for resolution.
- `context_switch_attempted`: whether runtime attempted a context change.
- `context_switch_result`: enum-like result (`not_attempted|success|failed|stale|unsupported|deferred`).
- `fallback_to_native`: whether decision logic reverted to native path.

## 6) WebView/hybrid classification flow (future)

FrameworkDetector output should guide surface paths as follows:

1. **native-only** (`android_native`/`ios_native`):
   - stay in native path,
   - run native hierarchy resolver stack only.

2. **webview-only** (`webview`):
   - inspect webview context availability,
   - route to web-style resolver pipeline when context access is healthy.

3. **hybrid** (`hybrid`):
   - inventory native + webview contexts,
   - apply guarded switching strategy,
   - compare candidates from both surfaces using existing ranking machinery (no priority change in this design phase).

4. **unknown** (`unknown`):
   - fail safe to native path,
   - mark context decision as deferred/unsupported in diagnostics.

## 7) Future switching decision rules

### Stay in `NATIVE_APP` when
- detector confidence favors native,
- no `WEBVIEW_*` contexts exist,
- action type is known-native/system level,
- prior step signaled unstable webview switching.

### Inspect `WEBVIEW_*` contexts when
- detector indicates `webview` or `hybrid`,
- instruction semantics imply DOM-like targeting,
- context inventory shows viable webview entries.

### Switch temporarily when
- a single preferred webview context is deterministically selectable,
- switch preconditions are met (driver context list stable, target surface expected web).

### Switch back to native when
- webview resolution finishes (success or failure),
- an interrupt/system dialog is detected,
- webview state becomes stale or unavailable.

### Fail safely when
- switching errors occur,
- web DOM/accessibility snapshot unavailable post-switch,
- ambiguity persists across native/web candidates.

### Mark unsupported/deferred when
- environment lacks required webview automation support,
- context names exist but are non-actionable in current capability state,
- policy forbids switching in current execution mode.

## 8) Resolver strategy design (future)

- **Native context**: continue using `AppiumHierarchyResolver` for native hierarchy-based resolution.
- **WebView context**: route to web-style resolver path (DOM/accessibility abstraction) when available.
- **Hybrid mode**:
  - collect candidate sets per context,
  - annotate each with context metadata,
  - arbitrate through current pipeline contracts without changing resolver priority/order in this phase.

Important: this document defines routing intent only; no resolver runtime changes are introduced now.

## 9) Safety/privacy design

Future diagnostics must remain metadata-only and explicitly avoid sensitive payload material:
- no raw DOM dumps,
- no raw XML dumps,
- no screenshot bytes,
- no provider request/response payload bodies,
- context names sanitized/compact (e.g., `WEBVIEW_#1` optionally mapped from raw names for reporting),
- warnings/reasons represented by controlled labels.

This aligns with existing reporting sanitization direction.

## 10) Reporting/diagnostics design (safe fields)

Proposed report-safe fields (JSON/HTML):
- `surface_type` (`android_native|ios_native|webview|hybrid|system_dialog|unknown`)
- `available_context_count` (integer)
- `selected_context_type` (`native|webview|unknown`)
- `switch_status` (`not_attempted|success|failed|stale|unsupported|deferred`)
- `switch_reason` (compact enum-like reason)
- `fallback_reason` (if returned to native path)
- `warnings` (list of compact warning labels)

Design requirement: these fields remain additive internal diagnostics and must not require public schema changes in this phase.

## 11) Memory/signature impact (future)

To avoid cross-context pollution in future mobile memory signatures, include context-separating components:
- platform (`android|ios`),
- `surface_type`,
- `selected_context_type`,
- app package/bundle **safe hash** (never raw package/bundle in user-facing diagnostics if policy restricts),
- screen/activity/page signature token.

Result: memory learned from native view should not incorrectly dominate a subsequent webview step (and vice versa).

## 12) Benchmark impact

Phase 19M-C seed expansion already provides baseline coverage for WebView/hybrid-adjacent scenarios and ambiguity/fallback patterns. This is sufficient to validate diagnostics-only and dry-run routing sub-phases before real switching.

Later recommended seed additions (future phase, not now):
- multiple `WEBVIEW_*` contexts with only one actionable,
- stale webview context lifecycle,
- native/web duplicate label collision requiring surface arbitration,
- switch-interrupted-by-system-dialog cases.

## 13) Failure and fallback handling (future)

Define explicit outcomes:
- **context unavailable**: no webview contexts found when expected → remain native, record `unsupported`/`deferred`.
- **stale WebView context**: context disappears between inventory and use → mark `stale`, fallback native.
- **switch failure**: driver throws on switch → mark `failed`, fallback native.
- **DOM unavailable after switch**: switched successfully but no usable web snapshot → fallback native, warning.
- **native/web ambiguity**: both surfaces produce plausible candidates without deterministic winner → preserve current ambiguity behavior, attach context diagnostics.
- **system dialog interrupt**: system-owned dialog detected during switch flow → restore native/system-dialog-safe handling, mark interrupted.

## 14) Future implementation plan (proposed safe sequence)

1. **Metadata-only context inventory MVP**
   - capture/sanitize available and active context names,
   - no switching executed.

2. **FrameworkDetector integration MVP**
   - consume inventory + existing signals,
   - emit `surface_type` diagnostics only.

3. **Dry-run switch diagnostics**
   - evaluate whether switching *would* be attempted,
   - emit reasons/status without executing switch.

4. **Resolver routing design hardening**
   - finalize context-to-resolver contract and arbitration metadata,
   - still no live context switch.

5. **Actual switch implementation**
   - guarded temporary switch and guaranteed restore,
   - strict fallback behavior.

6. **Reporting + benchmark validation**
   - expose safe metadata in JSON/HTML,
   - validate against seed scenarios and ambiguity/fallback metrics.

## 15) Recommendation for next phase (19M-E)

**Recommended: Phase 19M-E = WebView context inventory metadata MVP.**

Rationale:
- lowest-risk step with high diagnostic value,
- prerequisite for both FrameworkDetector implementation MVP and eventual switch logic,
- maintains design-first progression without runtime behavior disruption.

Alternative ordering:
- FrameworkDetector implementation MVP can begin immediately after inventory metadata is available.
- SystemDialogHandler design can proceed in parallel as a separate design stream, but is not the most direct blocker for WebView switching readiness.

## GO / NO-GO

**GO for Phase 19M-E (WebView context inventory metadata MVP).**

This phase (19M-D) introduces documentation only and keeps runtime behavior unchanged.
