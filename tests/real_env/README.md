# Real Environment Smoke Harness (Phase 19M-M Skeleton)

## Purpose

This directory contains a **skeleton-only** harness for future real-environment smoke validation.
It is intentionally safe and skip-by-default, and does not execute real browser, Appium,
device, simulator/emulator, or cloud sessions.

## Enablement

Real-environment tests are disabled by default.

Set:

```bash
BUBBLEGUM_REAL_ENV=1
```

If `BUBBLEGUM_REAL_ENV` is unset or not equal to `1`, tests in `tests/real_env` skip with a clear reason.

## Environment Variables

- `BUBBLEGUM_REAL_ENV` — global opt-in gate (`1` to enable harness checks).
- `BUBBLEGUM_REAL_ENV_CONFIG` — optional config path override for future phases.
- `BUBBLEGUM_REAL_ENV_ARTIFACT_DIR` — optional artifact directory override for future phases.
- `BUBBLEGUM_APPIUM_SERVER_URL` — required for Android/iOS smoke targets.
- `BUBBLEGUM_ANDROID_APP` — Android app path for emulator smoke (alternative: package/activity vars).
- `BUBBLEGUM_ANDROID_PACKAGE` — Android app package when launching installed app.
- `BUBBLEGUM_ANDROID_ACTIVITY` — Android launcher activity when launching installed app.
- `BUBBLEGUM_ANDROID_DEVICE_NAME` — Android emulator/device name for Appium capabilities.
- `BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT` — optional native text/content-desc used for an opt-in click smoke assertion.
- `BUBBLEGUM_IOS_APP` — required for iOS target smoke skeleton.
- `BUBBLEGUM_CLOUD_PROVIDER` — required for cloud smoke skeleton.
- `BUBBLEGUM_CLOUD_USERNAME` — required for cloud smoke skeleton.
- `BUBBLEGUM_CLOUD_ACCESS_KEY` — required for cloud smoke skeleton.

## Marker Strategy

Markers used by this harness skeleton:

- `real_env`
- `web_smoke`
- `android_emulator`
- `ios_simulator`
- `android_device`
- `ios_device`
- `cloud_device`
- `hybrid_webview`
- `system_dialog`
- `slow`

## Command Examples

Default skip behavior:

```bash
pytest tests/real_env -q
```

Opt in to web smoke skeleton collection/execution:

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env -m "real_env and web_smoke" -q
```

Opt in to Android skeleton checks (still skip unless required env vars are present):

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env -m "real_env and android_emulator" -q
```


Opt in to web smoke reporting artifact validation (JSON + HTML under pytest tmp path):

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env/web/test_web_local_smoke.py -k reporting --playwright -q
```

Expected artifact behavior:

- Creates one JSON report and one HTML report in `tmp_path`.
- JSON report is parseable and contains only report-safe fields.
- HTML report contains safe summary content only (no raw DOM/page dump).

Reporting safety/privacy expectations for smoke artifacts:

- No screenshot bytes or base64 image payloads.
- No provider payload/request/response bodies.
- No raw WebView context names.
- No credentials or secrets.
- No raw page DOM leakage beyond intended safe summaries.

## Privacy and Safety Rules

The skeleton harness must not store or print:

- raw credentials,
- raw DOM,
- raw XML,
- screenshot bytes,
- raw context names,
- package/process names,
- provider payloads.

## Current Guardrails

- No runtime WebView switching is implemented.
- No `driver.switch_to.context` calls are introduced.
- No device/cloud/browser sessions are started.
- Missing required environment variables cause **skip**, not failure.

## Expected Skip Behavior

- Without `BUBBLEGUM_REAL_ENV=1`: all real-env skeleton tests skip.
- With `BUBBLEGUM_REAL_ENV=1` but incomplete target env vars: target tests skip.

## Future Roadmap

Future phases can build on this harness to add:

- local web smoke MVP,
- Android emulator smoke MVP,
- iOS simulator smoke MVP,
- cloud smoke MVP,
- system-dialog scenario coverage,
- hybrid metadata validations under real sessions.


## Android Emulator Smoke MVP (Phase 19M-Q)

Run Android emulator smoke (opt-in only):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://localhost:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=emulator-5554 \
BUBBLEGUM_ANDROID_APP=/path/to/app.apk \
pytest tests/real_env/android/test_android_emulator_smoke.py -q
```

Installed app launch variant:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://localhost:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=emulator-5554 \
BUBBLEGUM_ANDROID_PACKAGE=com.example.app \
BUBBLEGUM_ANDROID_ACTIVITY=.MainActivity \
pytest tests/real_env/android/test_android_emulator_smoke.py -q
```

Expected behavior:
- Skips by default unless `BUBBLEGUM_REAL_ENV=1`.
- Skips (does not fail) when required Android/Appium env vars are missing or Appium/emulator is unavailable.
- Collects mobile context using existing Appium adapter and validates safe app-state metadata keys:
  - `context_inventory`
  - `framework_detection`
  - `webview_switch_diagnostics`
  - `webview_switch_guardrails`
- Does **not** perform WebView context switching and does **not** call `driver.switch_to.context`.
- Optional action smoke runs only when `BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT` is provided; in that case missing target is a test failure.
