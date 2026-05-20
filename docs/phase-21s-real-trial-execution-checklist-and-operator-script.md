# Phase 21S — Real Trial Execution Checklist and Operator Script

## 1) Purpose
This checklist and optional operator script provide a safe, repeatable way to execute **real-environment WebView readiness trials** for Android, iOS, and cloud/pCloudy paths. The focus is to produce execution evidence without leaking secrets or committing sensitive artifacts.

## 2) Scope
This Phase 21S artifact covers:
- Android real trial execution.
- iOS real trial execution.
- Cloud/pCloudy real trial execution (provider-neutral harness).
- **Validate/extract only** trial flow.
- Readiness enabled through test/config environment.
- `execute` remains unwired.

Out of scope:
- New runtime WebView behavior.
- Expanded execute wiring.
- Provider-specific runtime logic changes.

## 3) Pre-run safety checklist
Before running any real trial:
- Keep secrets in a local shell/session only (never in tracked files).
- Do not commit credentials, tokens, or access keys.
- Do not commit raw cloud/Appium capabilities payloads.
- Do not commit raw page source/XML/screenshots from real runs.
- Verify the sample app exposes a stable WebView target screen/state.
- Verify expected validate text and extract reference are known and stable.
- Confirm Appium (or cloud session endpoint) availability before running.

## 4) Required environment variables

### Android
- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_ANDROID_DEVICE_NAME`
- `BUBBLEGUM_ANDROID_APP` **or** (`BUBBLEGUM_ANDROID_PACKAGE` + `BUBBLEGUM_ANDROID_ACTIVITY`)
- `BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT`
- `BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF`
- `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1`

### iOS
- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_IOS_DEVICE_NAME`
- `BUBBLEGUM_IOS_APP` **or** `BUBBLEGUM_IOS_BUNDLE_ID`
- `BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT`
- `BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF`
- `BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH=1`
- Optional: `BUBBLEGUM_IOS_PLATFORM_VERSION`
- Optional: `BUBBLEGUM_IOS_AUTOMATION_NAME`

### Cloud
- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_CLOUD_DEVICE=1`
- `BUBBLEGUM_CLOUD_PROVIDER=pcloudy|browserstack|saucelabs|lambdatest|generic`
- `BUBBLEGUM_CLOUD_USERNAME`
- `BUBBLEGUM_CLOUD_ACCESS_KEY`
- `BUBBLEGUM_CLOUD_PLATFORM=android|ios`
- `BUBBLEGUM_CLOUD_DEVICE_NAME`
- `BUBBLEGUM_CLOUD_APP` **or** `BUBBLEGUM_CLOUD_APP_ID`
- `BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1`
- `BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT`
- `BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF`
- `BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH=1`

## 5) Readiness configuration
Expected readiness settings for these trials:
- `webview_readiness_wait_enabled=True`
- `webview_context_wait_timeout_ms`
- `webview_context_poll_interval_ms`
- `webview_target_wait_timeout_ms`
- `max_context_refresh_attempts`
- `fail_closed_on_readiness_timeout=True`

## 6) Operator script usage
Optional script:
- `scripts/run_webview_readiness_real_trials.sh`

Examples:
- `scripts/run_webview_readiness_real_trials.sh android --dry-run`
- `scripts/run_webview_readiness_real_trials.sh android`
- `scripts/run_webview_readiness_real_trials.sh ios --dry-run`
- `scripts/run_webview_readiness_real_trials.sh cloud --dry-run`
- `scripts/run_webview_readiness_real_trials.sh all --dry-run`

## 7) Expected pass evidence
Successful evidence set should include:
- Real-env tests are **not skipped** when required vars are present.
- Readiness diagnostics are emitted.
- Strict-mode WebView switch is attempted.
- Restore is attempted (and restored on success path).
- Validate/extract paths run.
- JSON/HTML readiness summary artifacts exist.
- No raw context/source/capability/credential leakage in artifacts.
- `execute` remains unwired.

## 8) Failure triage
If a run fails, classify quickly:
- Missing env variable(s).
- Appium server unreachable.
- Device unavailable / session not allocated.
- App launch failed.
- WebView context missing.
- Readiness timeout.
- Switch failed.
- Restore failed.
- Artifact leakage assertion failed.
- Cloud auth/capability failure.

## 9) Evidence capture template
Copy/paste per run:

| date (UTC) | platform/provider | command | result | readiness status | switch status | restore status | artifact safety result | issues | GO/NO-GO |
|---|---|---|---|---|---|---|---|---|---|
| YYYY-MM-DD | android / ios / cloud(provider) | `pytest ...` | pass/fail/skip | observed/not observed | attempted/success/fail | attempted/success/fail | pass/fail | short note | GO/NO-GO |

## 10) Post-run checklist
After trial execution:
- Review generated artifacts locally before sharing.
- Do not commit generated sensitive outputs.
- Update Phase 21O/21P/21Q result docs with real outcomes.
- Update Phase 21R acceptance review with consolidated evidence.
- Keep failed logs sanitized before attaching to reports.
