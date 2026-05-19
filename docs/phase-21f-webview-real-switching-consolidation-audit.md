# Phase 21F — WebView Real Switching Consolidation Audit

## 1) Purpose

This audit consolidates the completed real WebView switching work after Android, iOS, and cloud smoke harness coverage, and records current readiness boundaries before any real sample-app trial execution.

## 2) Completed capability summary

The current track has delivered the following:

- Strict opt-in real WebView switching for **validate/extract** only (no default-on behavior).
- **Execute remains unwired** for real WebView switching.
- Real-driver switching helper support for controlled context transitions.
- Context reference resolution based on strict metadata matching.
- Restore-path handling with fail-closed behavior when restoration fails.
- Metadata/reporting sanitization for context and capability-related reporting safety.
- Android real-env smoke coverage for WebView switching paths.
- iOS real-env smoke coverage for WebView switching paths.
- Cloud provider-neutral real-env smoke coverage for WebView switching paths.

## 3) Current safety posture

Current safety posture is intentionally conservative:

- Default configuration is effectively a no-op for real WebView switching.
- Real switching path is constrained to validate/extract only.
- Execute path remains unwired.
- Strict opt-in is required to activate real switching behavior.
- Restore of prior context is required.
- `fail_closed_on_restore_failure=True` is expected.
- Raw context names are not emitted in reporting artifacts.
- JSON and HTML artifact safety checks exist.
- Cloud-oriented leakage checks exist for credentials/capabilities.

## 4) Test and validation baseline

Baseline expectations at this phase:

- `pytest --collect-only -q` expected: **988 collected**.
- Benchmark static/execution checks remain **12/12**.
- Object-seed diagnostics remain **44 cases** with **0 expected-status mismatches**.
- Real-env Android/iOS/cloud suites skip by default unless explicitly opted in.
- Full `pytest` in Codex container may require async plugin availability (known caveat when missing).

## 5) Provider coverage

Provider/test-surface coverage currently includes:

- Android local/emulator smoke.
- iOS simulator/device smoke.
- Cloud provider-neutral smoke harness.
- Cloud providers represented include **pCloudy**, **BrowserStack**, **Sauce Labs**, **LambdaTest**, and generic provider handling.

## 6) Remaining gaps

Known gaps before broad rollout:

- Not yet validated against a real sample Android WebView application trial.
- Not yet validated against a real sample iOS WebView application trial.
- Cloud provider real execution not yet proven end-to-end.
- No performance/timing stabilization pass completed yet.
- No execute-action WebView support (by design at this phase).
- No automatic context selection beyond strict metadata matching.
- No additional retry/wait strategy around WebView readiness beyond current behavior.

## 7) Risk matrix

| Risk | Current mitigation | Residual risk |
|---|---|---|
| Wrong WebView context selected | Strict metadata-based selection and opt-in gating | Medium |
| Context list changes during switch | Restore/fail-closed safeguards | Medium |
| Restore failure | Required restore + fail-closed on restore failure | Low/Medium |
| WebView target not loaded | Conservative no-op default and smoke validation boundaries | Medium |
| Provider context variance | Provider-neutral cloud harness and generic handling | Medium |
| iOS context naming variance | iOS smoke coverage and strict matching | Medium |
| Cloud credential leakage | Reporting sanitization + leakage checks in cloud path | Low |
| Accidental execute wiring | Execute intentionally unwired in current architecture | Low |
| Flaky WebView timing | Skip-by-default real-env tests and deferred stabilization phase | Medium/High |

## 8) GO/NO-GO assessment

**Assessment: Conditional GO** for **sample-app trial runbook preparation/execution** only, provided all of the following remain true:

- Current tests/baseline checks pass.
- Execute remains unwired.
- Real-env smoke tests remain skip-by-default.
- Provider-neutral cloud support remains intact.
- No raw context/credential leakage in artifacts.

If any of these conditions regress, status should be treated as **NO-GO** until corrected.

## 9) Recommended next sequence

Recommended follow-on phases:

1. **21G — Real WebView Sample App Trial Runbook**
2. **21H — Android Real Sample WebView Trial**
3. **21I — iOS Real Sample WebView Trial**
4. **21J — Cloud Provider Trial** (start with pCloudy; keep docs provider-neutral)
5. **21K — WebView Timing/Readiness Stabilization**

## 10) Files to inspect

Primary files reviewed for this audit scope:

- `bubblegum/adapters/mobile/appium/adapter.py`
- `bubblegum/core/mobile/webview_real_driver_switch.py`
- `bubblegum/reporting/json_report.py`
- `bubblegum/reporting/html_report.py`
- `tests/real_env/android/test_android_webview_switch_smoke.py`
- `tests/real_env/ios/test_ios_webview_switch_smoke.py`
- `tests/real_env/cloud/test_cloud_webview_switch_smoke.py`
- `tests/real_env/cloud/harness.py`
- `tests/real_env/README.md`
