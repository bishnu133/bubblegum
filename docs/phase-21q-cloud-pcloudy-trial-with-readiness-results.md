# Phase 21Q — Cloud/pCloudy Trial with Readiness Results

## 1. Purpose

This document defines the execution-ready cloud real-environment WebView trial for strict opt-in validate/extract with readiness enabled, using pCloudy as the first recommended provider while preserving provider-neutral cloud runtime behavior.

This phase is intentionally documentation/trial-focused and does **not** broaden execute wiring, does **not** alter resolver/ranker/scoring/confidence, does **not** alter memory lookup behavior, does **not** add dependencies, and does **not** change package version.

## 2. Trial scope

In scope:
- Real cloud run of strict opt-in validate/extract smoke path with readiness enabled:
  - `test_cloud_webview_switch_smoke_validate_extract_real_env`
- Real cloud run of artifact safety coverage:
  - `test_cloud_webview_switch_reporting_artifacts_are_safe`
- Verification that readiness diagnostics are emitted and artifacts remain sanitized.
- pCloudy-first execution recommendation with provider-neutral compatibility retained.

Out of scope:
- Execute-path WebView runtime wiring changes.
- Provider-specific runtime branching unless a small, isolated, justified fix is required.
- Resolver/ranker/scoring/confidence changes.
- Memory lookup behavior changes.
- Dependency/version changes.

## 3. Provider priority

Provider execution priority for this phase:
1. **pCloudy** (first target)
2. BrowserStack
3. Sauce Labs
4. LambdaTest
5. Generic cloud/Appium-compatible provider

Provider policy:
- Runtime behavior must remain provider-neutral.
- pCloudy is the first recommended execution target for this trial, but not a runtime-only path.
- Any provider-specific deviation must be isolated, justified, and documented before proposing runtime code changes.

## 4. Sample app / screen details

Record these before execution:
- Sample app identifier/name: `<placeholder>`
- Sample app build/version: `<placeholder>`
- Cloud app reference (`APP` or `APP_ID`): `<placeholder>`
- Platform under trial (`android` or `ios`): `<placeholder>`
- Device name in provider catalog: `<placeholder>`
- Entry route/screen: `<placeholder>`
- WebView target screen path: `<placeholder>`
- Validate text expected on screen: `<placeholder>`
- Extract reference expected on screen: `<placeholder>`

Sample requirements:
- Hybrid/native mobile app with a WebView transition.
- Stable validate text for strict validate check.
- Stable extract reference for extract check.
- Known provider app upload/ID mapping.

## 5. Environment variables used, placeholders only

Required:
- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_CLOUD_DEVICE=1`
- `BUBBLEGUM_CLOUD_PROVIDER=pcloudy`
- `BUBBLEGUM_CLOUD_USERNAME=<placeholder>`
- `BUBBLEGUM_CLOUD_ACCESS_KEY=<placeholder>`
- `BUBBLEGUM_CLOUD_PLATFORM=android|ios`
- `BUBBLEGUM_CLOUD_DEVICE_NAME=<placeholder>`
- `BUBBLEGUM_CLOUD_APP=<placeholder>` **or** `BUBBLEGUM_CLOUD_APP_ID=<placeholder>`
- `BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT=<placeholder>`
- `BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF=<placeholder>`
- `BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH=1`

Optional:
- `BUBBLEGUM_CLOUD_WEBVIEW_ALLOWED_OPERATION=validate|extract`
- `BUBBLEGUM_CLOUD_WEBVIEW_EXPECT_STATUS=<placeholder>`
- `BUBBLEGUM_CLOUD_APPIUM_URL=<placeholder>`
- `BUBBLEGUM_APPIUM_SERVER_URL=<placeholder>` (generic/provider override)

## 6. Readiness configuration used

Required trial configuration (placeholders retained where environment-specific):
- `webview_readiness_wait_enabled=True`
- `webview_context_wait_timeout_ms=<placeholder, e.g. 5000>`
- `webview_context_poll_interval_ms=<placeholder, e.g. 250>`
- `webview_target_wait_timeout_ms=<placeholder, e.g. 5000>`
- `max_context_refresh_attempts=<placeholder, e.g. 1>`
- `fail_closed_on_readiness_timeout=True`

Notes:
- Readiness remains strict opt-in and default-off outside explicit configuration.
- Execute remains unwired in this phase.
- Cloud harness remains provider-neutral.

## 7. Commands executed

Cloud trial commands:
- `pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_smoke_validate_extract_real_env -q`
- `pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_reporting_artifacts_are_safe -q`

Required validation commands:
- `python scripts/validate_package.py`
- `pytest tests/unit/test_webview_readiness.py -q`
- `pytest tests/unit/test_webview_real_driver_adapter_wiring.py -q`
- `pytest tests/unit/test_json_report.py -q`
- `pytest tests/unit/test_phase19n_cloud_smoke_harness.py -q`
- `pytest --collect-only -q`
- `python scripts/run_benchmarks.py`
- `python scripts/run_benchmarks.py --execute`
- `python scripts/run_object_seed_diagnostics.py --cases tests/benchmarks/object_intelligence/seed_cases.json --synthetic-elements tests/benchmarks/object_intelligence/synthetic_elements.json`
- `git diff --check`

Execution status in this phase update:
- **Prepared, not executed** (cloud credentials/device/app/provider endpoint values not provided in this change).

## 8. Expected success criteria

- Cloud test does not skip when env vars are set.
- pCloudy/cloud session starts.
- WebView context becomes available.
- Readiness diagnostics emitted.
- Readiness status is `context_available`, `waiting_for_target`, or `target_ready` (implementation-dependent).
- Validate/extract path runs.
- Switch attempted when strict mode enabled.
- Restore attempted and restored.
- JSON/HTML artifacts include `webview_readiness_summary`.
- No username/access key leakage.
- No raw capabilities/context/source/screenshot leakage.
- Execute remains unwired.
- Provider-neutral harness remains intact.

## 9. Actual result template

Populate only after real cloud trial execution:

- Execution timestamp (UTC): `<placeholder>`
- Operator: `<placeholder>`
- Provider: `<placeholder>`
- Platform: `<placeholder>`
- Device name: `<placeholder>`
- Appium/provider endpoint: `<placeholder>`
- Sample app/screen: `<placeholder>`

Test outcomes:
- `test_cloud_webview_switch_smoke_validate_extract_real_env`: `<pass|fail|skip>`
- `test_cloud_webview_switch_reporting_artifacts_are_safe`: `<pass|fail|skip>`

Observed readiness diagnostics:
- Context discovery notes: `<placeholder>`
- Readiness status observed: `<placeholder>`
- Target wait notes: `<placeholder>`
- Restore notes: `<placeholder>`

Artifact checks:
- JSON includes `webview_readiness_summary`: `<yes|no>`
- HTML includes readiness summary section: `<yes|no>`
- Sensitive data leakage observed: `<yes|no>`

Overall trial status:
- `<pass|fail|blocked|prepared, not executed>`

## 10. Readiness diagnostics checklist

Mark complete after trial:
- [ ] Readiness enabled explicitly for trial run.
- [ ] Context wait diagnostics present.
- [ ] Target wait diagnostics present when target is delayed.
- [ ] Final readiness status recorded (`context_available`, `waiting_for_target`, or `target_ready` as emitted).
- [ ] Strict switch attempt logged when required switch is enabled.
- [ ] Restore attempt + restore result logged.
- [ ] Validate/extract execution confirmed after readiness step.

## 11. Artifact safety checklist

Mark complete after trial:
- [ ] JSON artifact includes `webview_readiness_summary`.
- [ ] HTML artifact includes readiness summary content.
- [ ] No username/access key leakage in logs/artifacts.
- [ ] No raw WebView context dumps with sensitive values.
- [ ] No raw page source dumps containing secrets/credentials.
- [ ] No capability blobs exposing sensitive infra/provider data.
- [ ] No raw screenshot/content leakage beyond sanitized reporting policy.

## 12. Failure triage

If trial fails or skips unexpectedly:
1. Confirm all required env vars are set (including strict require switch).
2. Confirm provider endpoint/Appium URL reachability and session creation.
3. Confirm provider account auth (`USERNAME`/`ACCESS_KEY`) and quota/session availability.
4. Confirm platform/device name matches provider catalog spelling and availability.
5. Confirm cloud app reference is valid (`APP` vs `APP_ID`).
6. Confirm sample app navigation reaches intended WebView screen.
7. Increase readiness timeouts conservatively if context discovery is timing-limited.
8. Verify validate text and extract ref map to stable on-screen values.
9. Confirm artifacts contain readiness summary and remain sanitized.
10. If provider-specific behavior differs, isolate and document without broadening provider-specific runtime paths.

## 13. GO/NO-GO decision

Current decision for this phase update:
- **Execution sign-off:** **NO-GO** (real cloud trial not executed in this update).
- **Trial readiness:** **GO** (commands, placeholders, readiness config, diagnostics checklist, and artifact checklist are prepared for pCloudy-first cloud execution).

## 14. Next action recommendation

- Run the two cloud trial commands once pCloudy credentials/device/app are available.
- Record actual outcomes in Section 9 without inventing results.
- If Section 8 criteria are met with clean artifact safety checks, mark GO for cloud/pCloudy readiness trial.
- Preserve provider-neutral runtime behavior across pCloudy/BrowserStack/Sauce Labs/LambdaTest/generic providers.
- Next phase recommendation: **Phase 21R — Real Trial Results Consolidation and Readiness Acceptance Review**.
