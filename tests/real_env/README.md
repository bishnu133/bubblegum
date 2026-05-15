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
- `BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT` — optional target hint for bounded Android scroll smoke search.
- `BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS` — optional max bounded scroll attempts (default `3`, clamped to safe bounds).
- `BUBBLEGUM_ANDROID_ENABLE_SCROLL_ACTION` — set to `1` to enable explicit bounded scroll action (default is metadata-only, no scroll action).
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


Android emulator reporting validation (JSON + HTML under pytest tmp path):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://localhost:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=emulator-5554 \
BUBBLEGUM_ANDROID_APP=/path/to/app.apk \
pytest tests/real_env/android/test_android_emulator_smoke.py -k reporting -q
```

Expected artifact behavior for Android reporting smoke:

- Creates one JSON report and one HTML report under pytest `tmp_path`.
- JSON is parseable and includes only report-safe Android app-state metadata:
  - `context_inventory`
  - `framework_detection`
  - `webview_switch_diagnostics`
  - `webview_switch_guardrails`
- HTML contains a safe summary (`Android Emulator Smoke Report`) and no raw XML/bytes/context names.
- Test skips clearly when real-env is disabled, required Android/Appium env vars are missing, or Appium/emulator runtime is unavailable.

Android reporting safety/privacy expectations:

- No raw hierarchy XML or screenshot bytes are persisted.
- No raw context names (for example `WEBVIEW_com.example.app`).
- No package/process names.
- No credentials/secrets or provider payload bodies.
- No WebView context switching (`driver.switch_to.context`) is performed.


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


## Web Local Smoke CI Commands

This project now includes opt-in local web smoke coverage in `tests/real_env/web/test_web_local_smoke.py`.
These tests stay disabled by default and are intended for explicit CI/dev opt-in only.

### Command matrix

Default PR CI (keep real-env disabled):

```bash
pytest -q
pytest tests/real_env -q
```

Expected result: baseline suite runs normally; `tests/real_env` is skipped unless `BUBBLEGUM_REAL_ENV=1` is set.

Manual developer opt-in (web smoke only):

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env/web -q
```

Manual developer opt-in with explicit Playwright marker:

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env/web -m playwright -q
```

Optional nightly web smoke (example CI job):

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env/web -m "real_env and web_smoke and playwright" -q
```

Release-candidate web smoke + reporting artifact validation:

```bash
BUBBLEGUM_REAL_ENV=1 pytest tests/real_env/web/test_web_local_smoke.py -k reporting -m playwright -q
```

### Browser runtime setup (example only)

If Playwright is installed but browser binaries are missing, smoke tests may skip with a runtime-availability message.
Example local setup:

```bash
python -m playwright install chromium
```

This is documentation-only guidance; no dependency or install step is enforced by default CI.

### Expected pass/skip behavior

- `BUBBLEGUM_REAL_ENV` unset: all `tests/real_env` tests skip.
- `BUBBLEGUM_REAL_ENV=1` and Playwright/browser available: web smoke tests run and should pass.
- `BUBBLEGUM_REAL_ENV=1` but Playwright module missing: tests skip via `pytest.importorskip`.
- `BUBBLEGUM_REAL_ENV=1` and Playwright module present but browser runtime missing: tests skip with a browser runtime message.

### Reporting artifact validation expectations

`test_web_local_smoke_reporting_artifacts_are_safe` validates:

- one JSON report file and one HTML report file are written under pytest `tmp_path`;
- reports contain safe summary/analytics content only;
- no credentials/secrets, no raw DOM/XML, no raw context identifiers, and no screenshot bytes are persisted.

### Troubleshooting

- **Skipped: real-env not enabled**
  - Set `BUBBLEGUM_REAL_ENV=1` for explicit opt-in runs.
- **Skipped: Playwright not selected in your workflow**
  - Use `-m playwright` (marker selection) when you want to scope to Playwright smoke tests.
- **Skipped: browser runtime missing**
  - Install local browser binaries (example: `python -m playwright install chromium`).
- **Verify baseline collection count**
  - Run `pytest --collect-only -q` and confirm the expected collection baseline for the current phase.
- **Find artifact output path during tests**
  - Reporting artifact checks use pytest `tmp_path`; generated JSON/HTML files are ephemeral per-test temp files.

### Safety and privacy reminder

- Web smoke coverage uses local static HTML (`page.set_content`) only.
- No external website access is required.
- No credentials are required.
- No screenshots are captured unless a future phase explicitly enables them.
- No raw DOM/XML/context names/provider payloads should appear in generated reports.


## Android Emulator Smoke CI Commands

These Android smoke tests are **opt-in** and remain disabled by default in PR CI.

### Command matrix

Default PR CI (real-env remains disabled):

```bash
pytest -q
```

Android smoke default skip check (real-env tree without opt-in):

```bash
pytest tests/real_env/android -q
```

Local Android emulator opt-in smoke run:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
pytest tests/real_env/android -q
```

Local Android emulator opt-in smoke run (installed app variant):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_PACKAGE=<app-package> \
BUBBLEGUM_ANDROID_ACTIVITY=<launcher-activity> \
pytest tests/real_env/android -q
```

Android reporting artifact validation (release-candidate style):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
pytest tests/real_env/android/test_android_emulator_smoke.py -k reporting -q
```

Android system-dialog detection smoke (metadata-only, no auto-click):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
pytest tests/real_env/android/test_android_emulator_smoke.py -k system_dialog_detection -q
```

Optional strict expectation mode (requires a visible Android system dialog):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_EXPECT_SYSTEM_DIALOG=1 \
pytest tests/real_env/android/test_android_emulator_smoke.py -k system_dialog_detection -q
```

Expected system-dialog smoke behavior:

- Test is skip-by-default unless `BUBBLEGUM_REAL_ENV=1`.
- Test skips clearly if Appium server URL, Android device name, or app launch inputs are missing.
- Test validates `system_dialog_detection` metadata is present and structured safely.
- By default, dialog detection may be true or false; the test only requires metadata presence/safety.
- With `BUBBLEGUM_ANDROID_EXPECT_SYSTEM_DIALOG=1`, test fails clearly unless `dialog_detected` is `true`.
- Test does **not** click/accept/deny/dismiss any system dialog and does **not** perform WebView context switching.

Optional target-text command (native click assertion):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT="Continue" \
pytest tests/real_env/android/test_android_emulator_smoke.py -q
```

Optional nightly Android emulator smoke example:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
pytest tests/real_env/android -m "real_env and android_emulator" -q
```

### Expected pass/skip behavior

- `BUBBLEGUM_REAL_ENV` unset: Android real-env tests skip.
- `BUBBLEGUM_REAL_ENV=1` but missing required Android/Appium vars: tests skip with a required-env reason.
- `BUBBLEGUM_REAL_ENV=1` with valid runtime: smoke tests execute normally.
- `BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT` unset: target-click assertion is not required.
- `BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT` set and target missing: test fails with explicit lookup/match failure.

### Troubleshooting

- **Skipped because `BUBBLEGUM_REAL_ENV` is not set**
  Set `BUBBLEGUM_REAL_ENV=1` for explicit opt-in.
- **Skipped because Android/Appium env vars are missing**
  Provide `BUBBLEGUM_APPIUM_SERVER_URL`, `BUBBLEGUM_ANDROID_DEVICE_NAME`, and either `BUBBLEGUM_ANDROID_APP` or `BUBBLEGUM_ANDROID_PACKAGE` + `BUBBLEGUM_ANDROID_ACTIVITY`.
- **Skipped because Appium server is not running/reachable**
  Start Appium (for example on `http://127.0.0.1:4723`) and rerun.
- **Skipped because emulator/device is unavailable**
  Ensure the named emulator/device is running and accessible by Appium.
- **Skipped/fails because app path/package/activity is invalid**
  Verify APK path exists, or confirm package/activity values launch correctly on the selected device.
- **Target text behavior**
  When `BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT` is set, lookup errors or no matches are assertion failures by design.

### Collect-only and artifact location checks

Verify current test collection baseline:

```bash
pytest --collect-only -q
```

Expected baseline after Phase 19M-W is **741 collected tests**.

For reporting validation (`-k reporting`), JSON/HTML outputs are written under pytest `tmp_path`.
Those files are test-temporary paths and are not persisted unless copied out during the run.

### Safety and privacy reminder

- Keep credentials out of repo config files (env-var references only in templates).
- Production apps are not required for initial Android smoke bring-up.
- No raw XML/hierarchy dump in report payloads.
- No screenshot bytes unless a future explicit config enables screenshots.
- No raw WebView context names.
- No package/process leakage.
- No runtime WebView switching (`driver.switch_to.context`).


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


Android scroll discovery smoke (metadata-only by default):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
pytest tests/real_env/android/test_android_scroll_smoke.py -q
```

Android bounded scroll action smoke (explicit opt-in):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_ENABLE_SCROLL_ACTION=1 \
BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT=Settings \
BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS=3 \
pytest tests/real_env/android/test_android_scroll_smoke.py -q
```

Android scroll smoke safety rules:

- Skip by default unless `BUBBLEGUM_REAL_ENV=1` and required Appium/device/app env vars are set.
- Default mode validates `scroll_discovery` metadata only and performs no scroll action.
- Bounded scroll action only runs when both `BUBBLEGUM_ANDROID_ENABLE_SCROLL_ACTION=1` and `BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT` are provided.
- Scroll attempts are bounded by `BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS` (safe clamp enforced).
- No WebView switching is used; no `driver.switch_to.context` calls.
- No raw XML, screenshot bytes, package/process/context identifiers, or credentials are emitted.
