# Phase 21H — Android Real Sample WebView Trial Results

## 1. Purpose

This document captures the execution-ready trial plan and result template for validating Android real-environment WebView switching on a sample app using the existing strict opt-in validate/extract smoke coverage from Phase 21B and reporting artifact safety checks from Phase 21D.

This phase intentionally limits scope to trial execution and documentation only. It does not broaden execute wiring and does not alter resolver/ranker/scoring/confidence, memory lookup behavior, dependencies, or package version.

## 2. Trial scope

In scope:
- Real Android sample-app run of the existing smoke test:
  - `test_android_webview_switch_smoke_validate_extract_real_env`
- Real Android sample-app run of the existing artifact safety test:
  - `test_android_webview_switch_reporting_artifacts_are_safe`
- Verification that trial setup and outputs preserve artifact safety expectations.

Out of scope:
- Any execute-path WebView runtime wiring expansion.
- Any behavior changes to resolver/ranker/scoring/confidence.
- Any memory lookup behavior changes.
- Any dependency changes.
- Any package version change.

## 3. Sample app / screen details

Use a real Android sample app/screen that satisfies all of the following:
- The app contains a hybrid/native + WebView flow.
- The target screen exposes stable validate text suitable for strict opt-in validation.
- The target screen includes a stable extraction reference for extract checks.
- The activity/package launch parameters are known (if app path install is not used).

Record before execution:
- Sample app identifier: `<placeholder>`
- Sample app build/version: `<placeholder>`
- Target screen name/path: `<placeholder>`
- Validate text source on screen: `<placeholder>`
- Extract reference source on screen: `<placeholder>`

## 4. Environment variables used (placeholders only)

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

Optional:
- `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1`

## 5. Commands executed

Validation/preflight:
- `pytest --collect-only -q`
- `git diff --check`

Trial commands:
- `pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_smoke_validate_extract_real_env -q`
- `pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_reporting_artifacts_are_safe -q`

Example execution block (placeholders only):

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL=<placeholder>
export BUBBLEGUM_ANDROID_DEVICE_NAME=<placeholder>
# Either app path:
export BUBBLEGUM_ANDROID_APP=<placeholder>
# Or package/activity:
# export BUBBLEGUM_ANDROID_PACKAGE=<placeholder>
# export BUBBLEGUM_ANDROID_ACTIVITY=<placeholder>
export BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1
export BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT=<placeholder>
export BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF=<placeholder>
# Optional strict requirement:
# export BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1

pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_smoke_validate_extract_real_env -q
pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_reporting_artifacts_are_safe -q
```

Execution status for this phase update:
- **Prepared, not executed** (real-device/Appium/sample-app specifics not supplied in this update).

## 6. Expected success criteria

1. Validate/extract real-env smoke test passes with strict opt-in controls enabled.
2. Reporting artifact safety test passes.
3. No sensitive values are leaked into generated artifacts.
4. No code-path broadening beyond current strict opt-in validate/extract behavior.

## 7. Actual result template

Use this template when a real trial run is performed:

- Execution date/time (UTC): `<placeholder>`
- Operator: `<placeholder>`
- Device: `<placeholder>`
- Appium endpoint: `<placeholder>`
- Sample app + screen: `<placeholder>`

Command outcomes:
- `test_android_webview_switch_smoke_validate_extract_real_env`: `<pass|fail|skip>`
- `test_android_webview_switch_reporting_artifacts_are_safe`: `<pass|fail|skip>`

Observed notes:
- WebView context(s) seen: `<placeholder>`
- Validate text check notes: `<placeholder>`
- Extract reference check notes: `<placeholder>`
- Artifact review summary: `<placeholder>`

Overall trial outcome:
- `<pass|fail|blocked>`

## 8. Artifact safety checklist

Before marking GO, confirm all items:
- [ ] No secrets/tokens/credentials included in test logs.
- [ ] No raw sensitive user or account data copied to artifacts.
- [ ] Validate/extract placeholders or approved sample-safe values only.
- [ ] Report attachments/screenshots reviewed for unintended data exposure.
- [ ] Trial output retained per project-safe handling expectations.

## 9. Failure triage

If either trial command fails:
1. Confirm Appium server reachability and session creation.
2. Confirm device name/capabilities match connected device.
3. Confirm sample app install/launch configuration (`APP` vs `PACKAGE/ACTIVITY`).
4. Confirm target screen navigation and readiness timing.
5. Confirm `BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT` matches stable on-screen text.
6. Confirm `BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF` is valid and stable.
7. Re-run with optional `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1` only when switch enforcement is intentionally required.
8. Capture failure artifacts and map to existing 21B/21D expectations before proposing any code change.

## 10. GO/NO-GO decision

Current decision for this update:
- **NO-GO for execution sign-off** (trial run not yet executed).
- **GO for readiness** (commands, env placeholders, and safety checklist are prepared).

## 11. Next action recommendation

Next recommended action:
1. Provision Appium endpoint, Android device/emulator, and sample hybrid app/screen values.
2. Execute the two Android trial commands exactly as listed in Section 5.
3. Fill Section 7 with real outcomes.
4. Re-evaluate GO/NO-GO based on real command results and checklist completion.
