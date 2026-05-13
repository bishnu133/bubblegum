# Phase 19M-B — FrameworkDetector Design (Detection-Only)

## 1) Problem statement

Bubblegum’s current mobile object intelligence is reliable for simple Android-native text/content-desc/resource-id matches, but it does not explicitly identify the active automation surface before matching. This causes ambiguity and fragility in scenarios where the same Appium session can encounter different surfaces (native screen, WebView, hybrid wrapper, system permission dialog, or unknown state). A surface-aware detector is needed so later phases can choose the right attribute strategy, diagnostics, and memory semantics without introducing non-deterministic behavior.

## 2) Scope

This phase defines **FrameworkDetector design only**:
- Detection/classification only (no action execution behavior).
- Metadata-only output suitable for safe reporting.
- No resolver order, no confidence/ranking changes, no adapter behavior changes.
- No schema/public API changes in this phase.

## 3) Non-goals

- No WebView context switching implementation.
- No system dialog handler implementation.
- No icon-only resolver implementation.
- No scoring/ranking/confidence model changes.
- No public API/schema changes.

## 4) Proposed FrameworkDetector responsibility

FrameworkDetector will evaluate **available deterministic signals** and classify current surface as one of:
- `android_native`
- `ios_native`
- `webview`
- `hybrid`
- `system_dialog`
- `unknown`

Primary evidence sources (in priority order):
1. Driver/session capabilities (platformName, automationName, appPackage, bundleId).
2. Current context name(s) if available (`NATIVE_APP`, `WEBVIEW_*`, etc.).
3. Hierarchy root/node signatures from page source (XML tags/attributes/classes).
4. Activity/package/bundle hints.
5. Known platform-owned dialog indicators.

Detector should tolerate missing inputs and degrade to `unknown` with low confidence and warnings.

## 5) Proposed output schema (internal metadata shape)

```json
{
  "surface_type": "android_native | ios_native | webview | hybrid | system_dialog | unknown",
  "platform": "android | ios | unknown",
  "framework": "uiautomator2 | xcuitest | chromedriver_webview | mixed | unknown",
  "confidence": 0.0,
  "evidence": [
    "cap:platformName=Android",
    "ctx:NATIVE_APP",
    "xml:attr:resource-id",
    "pkg:com.example.app"
  ],
  "warnings": [
    "missing_context_names",
    "conflicting_surface_signals"
  ],
  "safe_metadata_only": true
}
```

Notes:
- Evidence must be compact tokenized facts (not raw XML, DOM, screenshots, payload bodies).
- `confidence` is detector confidence only (not target-confidence/ranker confidence).
- `safe_metadata_only` is always `true` by design intent.

## 6) Surface classification rules

### Android native
Strong signals:
- `platformName=Android`.
- Context is `NATIVE_APP`.
- Hierarchy includes Android UI classes (`android.widget.*`) and attributes like `resource-id`, `content-desc`, `bounds`.
- Activity/package looks app-owned and not browser/webview-only.

Classify `android_native` when Android-native signals dominate and no strong webview/system-dialog override exists.

### iOS native
Strong signals:
- `platformName=iOS`.
- Context is `NATIVE_APP`.
- Hierarchy patterns consistent with XCUI element tree (`XCUIElementType*`) and iOS attrs (`name`, `label`, `value`, `visible`, `enabled`).
- BundleId hints app-owned native view.

Classify `ios_native` when iOS-native signals dominate and no strong webview/system-dialog override exists.

### WebView
Strong signals:
- Active context `WEBVIEW_*`.
- Driver contexts show only webview contexts or current context is webview.
- Hierarchy/class/package hints to Chromium/WebKit web layer.

Classify `webview` when web-context signals are dominant and no concurrent strong native evidence for mixed mode.

### Hybrid
Strong signals:
- Both native and webview contexts are available in same session.
- Current snapshot/hints suggest native container plus embedded web surface.
- Surface indicators conflict between native hierarchy and webview context hints.

Classify `hybrid` when meaningful mixed evidence exists, especially with both `NATIVE_APP` and `WEBVIEW_*` present.

### System dialog
Strong signals:
- Platform-owned package/bundle/activity hints for permissions/alerts.
- Permission-like text patterns (allow/deny/while using app/don’t allow/OK/cancel) detected in sanitized token form.
- Dialog-like class hints owned by OS/system UI.

Classify `system_dialog` when system-owned evidence outweighs app-owned evidence.

### Unknown
Use when:
- Evidence is sparse/incomplete.
- Signals conflict without clear dominance.
- Driver/session cannot provide sufficient deterministic cues.

## 7) Attribute-priority map by surface

### Android native
Priority emphasis:
1. `text`
2. `content-desc`
3. `resource-id`
4. `class`
5. `bounds`
6. `package`

### iOS native
Priority emphasis:
1. `name`
2. `label`
3. `value`
4. `type`
5. `visible`
6. `enabled`
7. `rect/bounds`

### WebView / hybrid
Priority emphasis:
1. context name/state
2. DOM/accessibility availability signal (presence only, no raw dump)
3. webview package/class hints
4. native wrapper/container hints

### System dialog
Priority emphasis:
1. package/class/activity ownership hints
2. permission phrase tokens
3. allow/deny button token patterns
4. platform-owned package/bundle hints

## 8) How detector later helps

1. **Resolver selection**: later phases can choose mobile resolver strategy based on surface classification.
2. **Attribute strategy**: use surface-specific match fields (Android vs iOS vs WebView).
3. **Memory signatures**: include surface/framework hints to avoid cross-surface cache pollution.
4. **Graph interpretation**: adjust relationship assumptions (e.g., list/card semantics differ by surface).
5. **Reporting diagnostics**: expose compact surface evidence and confidence for debuggability.
6. **Benchmark grouping**: measure pass/ambiguity rates by surface_type.

## 9) Safety/privacy design

FrameworkDetector evidence must remain sanitized:
- No raw page source.
- No raw screenshot bytes.
- No full XML/DOM dump.
- No provider payload/request/response bodies.
- Evidence is compact, normalized, and tokenized.
- Warnings and reasons are enumerated labels, not raw exception traces.

## 10) Suggested future integration points (future phases)

- Appium adapter context collection: append detector metadata to UIContext/step context internals.
- AppiumHierarchyResolver metadata: include detector result in candidate metadata diagnostics.
- StepResult metadata: surface detector output as safe fields.
- JSON/HTML reporting: include detector summary under safe diagnostics panels.
- Memory signature generation: optional surface tag injection for signature inputs.
- Benchmark diagnostics: split object-seed metrics by detected surface.

## 11) Phase 19M-C readiness recommendation

**Recommended next phase: mobile benchmark seed expansion first.**

Reasoning:
- The design is ready, but current seed coverage is web-heavy and Android-only for mobile slices.
- Expanding seed coverage for iOS, webview/hybrid, and system dialogs provides deterministic fixtures needed to validate any subsequent design/implementation (including WebView-switching design or dialog-handler design) without changing runtime behavior yet.

Suggested order:
1. Phase 19M-C: benchmark seed expansion (iOS + hybrid/webview + system dialog + icon-only + repeated/off-screen cases).
2. Follow-up: WebView context switching design.
3. Then: system dialog handler design.

## GO / NO-GO

**GO for Phase 19M-C** (with benchmark seed expansion as the immediate priority).
