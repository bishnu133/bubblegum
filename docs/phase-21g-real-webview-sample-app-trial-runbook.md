# Phase 21G — Real WebView Sample App Trial Runbook

## 1) Purpose

This runbook guides **safe, repeatable real sample-app trials** for strict opt-in WebView switching in Bubblegum.
It is specifically focused on **validate/extract operation paths** where real WebView context switching is allowed under current constraints.

## 2) Scope

This runbook covers:

- Android local/emulator sample app trial.
- iOS simulator/device sample app trial.
- Cloud provider trial.
- Validate/extract only.
- No execute support.

## 3) Non-goals

This phase does **not** include:

- Any runtime code change.
- Any execute WebView action support.
- Any resolver/ranker/scoring change.
- Any automatic WebView switching by default.

## 4) Prerequisites

Before running trials, ensure all of the following are true:

- Appium server is running and reachable.
- Android emulator/device or iOS simulator/device is available.
- Sample app exposes a stable WebView context.
- You have a known validate text target in the sample app WebView.
- You have a known extract ref/selector target in the sample app WebView.
- Environment variables are prepared for the selected platform/provider.
- No secrets are committed to git (credentials must stay local/ephemeral).

## 5) Android local/emulator trial setup

Set required environment variables:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723
export BUBBLEGUM_ANDROID_DEVICE_NAME="emulator-5554"

# Use either app path OR package/activity.
export BUBBLEGUM_ANDROID_APP="/path/to/sample.apk"
# export BUBBLEGUM_ANDROID_PACKAGE="com.example.sample"
# export BUBBLEGUM_ANDROID_ACTIVITY=".MainActivity"

export BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1
export BUBBLEGUM_ANDROID_WEBVIEW_VALIDATE_TEXT="Welcome"
export BUBBLEGUM_ANDROID_WEBVIEW_EXTRACT_REF="//android.webkit.WebView//*[@content-desc='sample-target']"

# Optional strict requirement: fail run if switch-ready path does not actually switch.
# export BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1
```

Notes:

- `BUBBLEGUM_ANDROID_WEBVIEW_REQUIRE_SWITCH=1` is optional and recommended for stricter trial gating.
- Keep validate/extract targets stable to reduce false negatives from app timing.

## 6) iOS simulator/device trial setup

Set required environment variables:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723
export BUBBLEGUM_IOS_DEVICE_NAME="iPhone 15"

# Use either app path OR bundle id.
export BUBBLEGUM_IOS_APP="/path/to/sample.app"
# export BUBBLEGUM_IOS_BUNDLE_ID="com.example.sample"

export BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE=1
export BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT="Welcome"
export BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF="//XCUIElementTypeWebView//*[@name='sample-target']"

# Optional strict requirement.
# export BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH=1
```

Notes:

- `BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH=1` is optional and useful for hard GO/NO-GO checks.
- Keep simulator/device and app build stable across comparison runs.

## 7) Cloud trial setup

Set provider-neutral required environment variables:

```bash
export BUBBLEGUM_REAL_ENV=1
export BUBBLEGUM_CLOUD_DEVICE=1
export BUBBLEGUM_CLOUD_PROVIDER="pcloudy"  # pcloudy|browserstack|saucelabs|lambdatest|generic
export BUBBLEGUM_CLOUD_USERNAME="<username>"
export BUBBLEGUM_CLOUD_ACCESS_KEY="<access-key>"
export BUBBLEGUM_CLOUD_PLATFORM="android"  # android|ios
export BUBBLEGUM_CLOUD_DEVICE_NAME="Pixel 7"

# Use either app path/url OR app id.
export BUBBLEGUM_CLOUD_APP="bs://<app-or-url>"
# export BUBBLEGUM_CLOUD_APP_ID="<provider-app-id>"

export BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1
export BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT="Welcome"
export BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF="//*[@id='sample-target']"
```

### Provider examples

#### pCloudy

```bash
export BUBBLEGUM_CLOUD_PROVIDER=pcloudy
# Optional: override default provider Appium URL.
# export BUBBLEGUM_CLOUD_APPIUM_URL="https://device.pcloudy.com/appiumcloud/wd/hub"
```

#### BrowserStack

```bash
export BUBBLEGUM_CLOUD_PROVIDER=browserstack
# Optional: override default provider Appium URL.
# export BUBBLEGUM_CLOUD_APPIUM_URL="https://hub.browserstack.com/wd/hub"
```

#### Sauce Labs

```bash
export BUBBLEGUM_CLOUD_PROVIDER=saucelabs
# Optional: override default provider Appium URL.
# export BUBBLEGUM_CLOUD_APPIUM_URL="https://ondemand.us-west-1.saucelabs.com/wd/hub"
```

#### LambdaTest

```bash
export BUBBLEGUM_CLOUD_PROVIDER=lambdatest
# Optional: override default provider Appium URL.
# export BUBBLEGUM_CLOUD_APPIUM_URL="https://mobile-hub.lambdatest.com/wd/hub"
```

#### generic

```bash
export BUBBLEGUM_CLOUD_PROVIDER=generic
# Required for generic provider mode.
export BUBBLEGUM_APPIUM_SERVER_URL="https://<custom-grid>/wd/hub"
# or
# export BUBBLEGUM_CLOUD_APPIUM_URL="https://<custom-grid>/wd/hub"
```

## 8) Commands to run

### Android smoke command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_smoke_validate_extract_real_env -q
```

### Android artifact command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_ANDROID_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/android/test_android_webview_switch_smoke.py::test_android_webview_switch_reporting_artifacts_are_safe -q
```

### iOS smoke command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/ios/test_ios_webview_switch_smoke.py::test_ios_webview_switch_smoke_validate_extract_real_env -q
```

### iOS artifact command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/ios/test_ios_webview_switch_smoke.py::test_ios_webview_switch_reporting_artifacts_are_safe -q
```

### Cloud smoke command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_smoke_validate_extract_real_env -q
```

### Cloud artifact command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_CLOUD_DEVICE=1 \
BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1 \
pytest tests/real_env/cloud/test_cloud_webview_switch_smoke.py::test_cloud_webview_switch_reporting_artifacts_are_safe -q
```

## 9) Expected success criteria

A successful trial should satisfy all applicable checks:

- Tests do not skip when all required environment variables are set.
- Validate/extract path runs.
- Switch is attempted when strict mode path is switch-ready.
- Restore is attempted and restore status indicates successful restoration.
- `webview_switch_wiring_plan` is present in metadata.
- `webview_switch_execution` is present when switch-ready path executes.
- JSON/HTML artifacts are safe.
- No raw context/credential leakage appears in artifacts.

## 10) Failure triage matrix

| Symptom | Typical cause | Triage actions |
|---|---|---|
| Test skipped | Missing opt-in or required env vars | Re-check `BUBBLEGUM_REAL_ENV=1`, platform/provider-specific smoke opt-in flags, and mandatory envs. |
| No WebView context found | App not on WebView screen, or context not ready | Navigate app to WebView host screen; add app-side readiness/wait; re-run with stable timing. |
| Switch not attempted | Path not switch-ready or metadata mismatch | Verify validate/extract targets and context selection metadata inputs; confirm strict opt-in envs are set. |
| Switch failed | Provider/device context switch failure | Inspect Appium/session logs, device state, and platform-specific context inventory behavior. |
| Restore failed | Original context unavailable or session instability | Treat as NO-GO; inspect context lifecycle and provider/device session consistency before retry. |
| Validate target not found | Wrong/missing text target | Confirm visible text in current app build and adjust `*_WEBVIEW_VALIDATE_TEXT`. |
| Extract ref invalid | Selector mismatch | Verify selector strategy against current DOM/accessibility tree and update `*_WEBVIEW_EXTRACT_REF`. |
| Cloud auth/session failed | Invalid credentials or endpoint | Re-issue ephemeral credentials, verify provider URL, and confirm account/device access entitlements. |
| Provider capability rejected | Namespace/capability incompatibility | Compare generated capabilities with provider requirements; use provider-specific optional env tuning. |
| Raw leakage assertion failed | Unsafe metadata or artifact content | Stop and treat as NO-GO; sanitize reporting path inputs and verify no secret/context leakage before rerun. |

## 11) Safety checklist

- Never commit credentials.
- Never commit raw Appium capabilities.
- Never commit raw page source.
- Never attach screenshots unless sanitized.
- Review JSON/HTML artifacts for leakage.
- Keep execute unwired.

## 12) Trial result template

Copy/paste template:

```text
Date:
Platform/Provider:
Device:
App build/reference:
Command:
Validate target:
Extract ref:
Result (pass/fail/skip):
Switch status:
Restore status:
Artifact paths:
Issues found:
GO/NO-GO decision:
```

## 13) GO/NO-GO criteria

### GO if

- Switch + restore works.
- Reports are safe.
- No execute behavior changed.
- No leakage.
- Failures (if any) are understood and bounded.

### NO-GO if

- Restore failure occurs.
- Raw context/credential leakage is detected.
- Switch behavior is inconsistent for stable input.
- Cloud provider rejects required capabilities with no safe configuration path.
- Test requires runtime behavior change outside this phase scope.

## 14) Recommended next phases

- **21H — Android Real Sample WebView Trial**
- **21I — iOS Real Sample WebView Trial**
- **21J — Cloud Provider Trial**, starting with pCloudy while keeping provider-neutral docs.
- **21K — WebView Timing/Readiness Stabilization**
