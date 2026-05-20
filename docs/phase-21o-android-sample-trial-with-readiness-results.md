# Phase 21O — Android Sample Trial with Readiness Results

## 1. Purpose

This document defines the execution-ready Android real-environment sample trial for strict opt-in WebView validate/extract with readiness enabled, and provides a result template for recording outcomes.

This phase is intentionally documentation/trial-focused and does **not** broaden execute wiring, does **not** alter resolver/ranker/scoring/confidence, does **not** alter memory lookup behavior, does **not** add dependencies, and does **not** change package version.

## 2. Trial scope

In scope:
- Real Android run of strict opt-in validate/extract smoke path with readiness enabled:
  - `test_android_webview_switch_smoke_validate_extract_real_env`
- Real Android run of artifact safety coverage:
  - `test_android_webview_switch_reporting_artifacts_are_safe`
- Verification that readiness diagnostics are emitted and artifacts remain sanitized.

Out of scope:
- Execute-path WebView runtime wiring changes.
- Resolver/ranker/scoring/confidence changes.
- Memory lookup behavior changes.
- Dependency/version changes.

## 3. Sample app / screen details

Record these before execution:
- Sample app identifier: `<placeholder>`
- Sample app build/version: `<placeholder>`
- Entry route/screen: `<placeholder>`
- WebView target screen path: `<placeholder>`
- Validate text expected on screen: `<placeholder>`
- Extract reference expected on screen: `<placeholder>`

Sample requirements:
- Hybrid/native app with a WebView transition.
- Stable validate text for strict validate check.
- Stable extract reference for extract check.
- Known launch mode (`APP` path or `PACKAGE` + `ACTIVITY`).

## 4. Environment variables used, placeholders only

Required:
- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL=<placeholder>`
- `BUBBLEGUM_ANDROID_DEVICE_NAME=<placeholder>`
- `BUBBLEGUM_ANDROID_APP=<placeholder>` **or** both:
  - `BUBBLEGUM_ANDROID_PACKAGE=<placeholder>`
  - `BUBBLEGUM_ANDROID_ACTIVITY=<placeholder>`
- `BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT=<placeholder>`
- `BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF=<placeholder>`
- `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1`

## 5. Readiness configuration used

Required trial configuration (placeholders retained where environment-specific):
- `webview_readiness_wait_enabled=True`
- `webview_context_wait_timeout_ms=<placeholder, e.g. 3000>`
- `webview_context_poll_interval_ms=<placeholder, e.g. 250>`
- `webview_target_wait_timeout_ms=<placeholder, e.g. 3000>`
- `max_context_refresh_attempts=<placeholder, e.g. 1>`
- `fail_closed_on_readiness_timeout=True`

Notes:
- Readiness remains strict opt-in and default-off outside explicit configuration.
- Execute remains unwired in this phase.

## 6. Commands executed

Trial commands:
- `pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_smoke_validate_extract_real_env -q`
- `pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_reporting_artifacts_are_safe -q`

Project validation commands:
- `python scripts/validate_package.py`
- `pytest tests/unit/test_webview_readiness.py -q`
- `pytest tests/unit/test_webview_real_driver_adapter_wiring.py -q`
- `pytest tests/unit/test_json_report.py -q`
- `pytest --collect-only -q`
- `python scripts/run_benchmarks.py`
- `python scripts/run_benchmarks.py --execute`
- `python scripts/run_object_seed_diagnostics.py --cases tests/benchmarks/object_intelligence/seed_cases.json --synthetic-elements tests/benchmarks/object_intelligence/synthetic_elements.json`
- `git diff --check`

Execution status in this phase update:
- **Blocked/prepared** (Phase 21T dry-run executed on 2026-05-20 UTC; required Android real-env variables/device/app were not present, so real trial execution was not run).

## 7. Expected success criteria

- Real Android test does not skip when required env vars are set.
- WebView context becomes available.
- Readiness diagnostics emitted.
- Readiness status is `context_available` or `waiting_for_target`/`target_ready` (implementation-dependent).
- Validate/extract path runs.
- Switch attempted when strict mode is enabled.
- Restore attempted and restored.
- JSON/HTML artifacts include `webview_readiness_summary`.
- No raw context/source/capability/credential leakage.
- Execute remains unwired.

## 8. Actual result (Phase 21T)

- Execution timestamp (UTC): `2026-05-20`
- Operator: `Codex agent`
- Device/emulator: `Not available in environment`
- Appium endpoint: `Not configured`
- Sample app/screen: `Sanitized: not configured in environment`

Commands run:
- `scripts/run_webview_readiness_real_trials.sh android --dry-run`
- `scripts/run_webview_readiness_real_trials.sh android` **not run** (blocked by missing prerequisites)

Dry-run environment check outcome:
- `BUBBLEGUM_REAL_ENV`: missing
- `BUBBLEGUM_APPIUM_SERVER_URL`: missing
- `BUBBLEGUM_ANDROID_DEVICE_NAME`: missing
- `BUBBLEGUM_ANDROID_APP`: missing
- `BUBBLEGUM_ANDROID_PACKAGE`: missing
- `BUBBLEGUM_ANDROID_ACTIVITY`: missing
- `BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE`: missing
- `BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT`: missing
- `BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF`: missing
- `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH`: missing

Test outcomes:
- `test_android_webview_switch_smoke_validate_extract_real_env`: `not executed` (prerequisites missing)
- `test_android_webview_switch_reporting_artifacts_are_safe`: `not executed` (prerequisites missing)

Observed readiness diagnostics:
- Context discovery notes: `Not observed in this environment (real run blocked)`
- Readiness status observed: `Not observed in this environment (real run blocked)`
- Target wait notes: `Not observed in this environment (real run blocked)`
- Restore notes: `Not observed in this environment (real run blocked)`

Artifact checks:
- JSON includes `webview_readiness_summary`: `not assessed` (no real run artifacts generated)
- HTML includes readiness summary section: `not assessed` (no real run artifacts generated)
- Sensitive data leakage observed: `no` (no real-run sensitive artifacts generated/committed in this phase)

Overall trial status:
- `blocked/prepared`

## 9. Readiness diagnostics checklist

Mark complete after trial:
- [ ] Readiness enabled explicitly for trial run. (Blocked: real env unavailable in this phase)
- [ ] Context wait diagnostics present. (Blocked: real env unavailable in this phase)
- [ ] Target wait diagnostics present when target is delayed. (Blocked: real env unavailable in this phase)
- [ ] Final readiness status recorded (`context_available`, `waiting_for_target`, or `target_ready` as emitted). (Blocked: real env unavailable in this phase)
- [ ] Strict switch attempt logged when required switch is enabled. (Blocked: real env unavailable in this phase)
- [ ] Restore attempt + restore result logged. (Blocked: real env unavailable in this phase)
- [ ] Validate/extract execution confirmed after readiness step. (Blocked: real env unavailable in this phase)

## 10. Artifact safety checklist

Mark complete after trial:
- [ ] JSON artifact includes `webview_readiness_summary`. (Blocked: no real-run artifacts)
- [ ] HTML artifact includes readiness summary content. (Blocked: no real-run artifacts)
- [ ] No raw WebView context dumps with sensitive values.
- [ ] No raw page source dumps containing secrets/credentials.
- [ ] No capability blobs exposing sensitive infra data.
- [ ] No credential/token leakage in logs or artifacts.

## 11. Failure triage

If trial fails or skips unexpectedly:
1. Confirm all required env vars are set (including strict require switch).
2. Confirm Appium endpoint reachability and session creation.
3. Confirm device name/capabilities match actual connected device/emulator.
4. Confirm app launch mode (`ANDROID_APP` vs `ANDROID_PACKAGE` + `ANDROID_ACTIVITY`).
5. Confirm sample app navigation reaches intended WebView screen.
6. Increase readiness timeouts conservatively if context discovery is timing-limited.
7. Verify validate text and extract ref map to stable on-screen values.
8. Confirm artifacts contain readiness summary and remain sanitized.
9. If behavior differs, capture logs/artifacts and compare against existing strict opt-in readiness unit coverage before any runtime code proposal.

## 12. GO/NO-GO decision

Current decision for this phase update (Phase 21T):
- **Execution sign-off:** **NO-GO** (Android real trial blocked due to missing required env/device/app prerequisites).
- **Trial readiness:** **GO** (operator script dry-run and documentation are prepared for immediate execution once prerequisites are provided).

## 13. Next action recommendation

- Run the two Android trial commands once device/Appium/sample app are available.
- Record actual outcomes in Section 8 without inventing results.
- If criteria in Section 7 are met with clean artifact safety checks, mark GO for Android sample readiness trial.
- Next phase recommendation: **Phase 21U — iOS Real Trial Execution with Readiness**.
