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
- `BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION` — set to `1` to enable explicit bounded scroll resolution smoke (default skip/metadata-only; no scroll by default).
- `BUBBLEGUM_IOS_APP` — required for iOS target smoke skeleton.
- `BUBBLEGUM_CLOUD_PROVIDER` — required for cloud smoke harness (`pcloudy`, `browserstack`, `saucelabs`, `lambdatest`, `generic`).
- `BUBBLEGUM_CLOUD_USERNAME` — required for cloud smoke skeleton.
- `BUBBLEGUM_CLOUD_ACCESS_KEY` — required for cloud smoke skeleton.


Cloud provider defaults for Phase 19N-Y smoke MVP:

- `pcloudy` -> `https://device.pcloudy.com/appiumcloud/wd/hub`
- `browserstack` -> `https://hub.browserstack.com/wd/hub`
- `saucelabs` -> `https://ondemand.us-west-1.saucelabs.com/wd/hub`
- `lambdatest` -> `https://mobile-hub.lambdatest.com/wd/hub`
- `generic` -> requires explicit `BUBBLEGUM_APPIUM_SERVER_URL`


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

Android repeated-region reporting artifact validation (JSON/HTML in pytest `tmp_path`):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1 \
BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT="<target text>" \
BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT="<anchor text>" \
pytest tests/real_env/android/test_android_repeated_region_smoke.py -k reporting_artifacts_are_safe -q
```

Expected skip behavior:

- Skips unless `BUBBLEGUM_REAL_ENV=1` and all Android/Appium vars are present.
- Skips unless repeated-region opt-in is explicit (`BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1`).
- Skips unless both repeated-region text hints are provided (`BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT` and `BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT`).

Repeated-region artifact expectations:

- Writes one JSON report and one HTML report under pytest `tmp_path` only.
- Validates JSON parseability, repeated-region analytics (`repeated_region_summary`), and `Repeated Region Diagnostics` HTML section presence.
- Enforces safety/privacy redaction: no raw hierarchy payloads, screenshots, provider payloads, raw context/package/process identifiers, credentials/secrets, or raw Appium capability payloads in generated artifacts.
- Screen under test must include repeated card/list/row-style structures so repeated-region diagnostics metadata can be produced safely.

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


Android scroll resolution opt-in smoke (explicit action only):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1 \
BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT="<visible-after-scroll-text>" \
BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS=3 \
pytest tests/real_env/android/test_android_scroll_smoke.py -k scroll_resolution_opt_in -q
```

Expected Android scroll resolution skip/safety behavior:

- Skips unless `BUBBLEGUM_REAL_ENV=1` and required Android/Appium env vars are set.
- Skips unless `BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1` is explicitly provided.
- Skips clearly when `BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT` is missing under opt-in mode.
- Uses bounded scrolling only via `BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS` (default `3`, clamped to safe bounds).
- Re-collects context and re-runs resolver checks after each bounded scroll attempt.
- Stops early when the target is found; fails clearly only when an explicit target is requested and not found within bounded attempts.
- May interact with the app only when explicit opt-in scroll resolution is enabled.


Android scroll resolution reporting artifact validation (JSON + HTML):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1 \
BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT="<visible-after-scroll-text>" \
BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS=3 \
pytest tests/real_env/android/test_android_scroll_smoke.py -k reporting_artifacts_are_safe -q
```

Expected behavior for reporting artifact validation:

- Skip-by-default unless real-env gate and Android/Appium launch vars are present.
- Additional explicit opt-in required: `BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1` and `BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT`.
- Generates one JSON report and one HTML report under pytest `tmp_path` (ephemeral per test run).
- JSON must parse and include analytics `scroll_resolution_summary` when scroll-resolution metadata exists.
- HTML must include scroll-resolution summary content only; no raw hierarchy/payload dumps.
- Artifacts must not include raw XML/DOM, screenshot bytes, provider payloads, package/process/context identifiers, raw capabilities, or credentials/secrets.

### Android repeated-region diagnostics smoke (Phase 19N-M)

This smoke is **skip-by-default** and is intended to validate safe repeated card/list/row diagnostics in a real Android Appium session.

Run command:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1 \
BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT="Buy" \
BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT="Product A" \
pytest tests/real_env/android/test_android_repeated_region_smoke.py -q
```

Installed-app variant:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_PACKAGE=<app-package> \
BUBBLEGUM_ANDROID_ACTIVITY=<launcher-activity> \
BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1 \
BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT="Buy" \
BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT="Product A" \
pytest tests/real_env/android/test_android_repeated_region_smoke.py -q
```

Required repeated-region opt-in vars:

- `BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1`
- `BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT`
- `BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT`

Optional controls:

- `BUBBLEGUM_ANDROID_REPEATED_ACTION_HINT` (default `tap`)
- `BUBBLEGUM_ANDROID_REPEATED_EXPECT_STATUS` (assert exact diagnostics status)
- `BUBBLEGUM_ANDROID_REPEATED_REQUIRE_RESOLVED=1` (strict mode)

Expected skip behavior:

- Skips when `BUBBLEGUM_REAL_ENV` is not `1`.
- Skips when required Android/Appium launch vars are missing.
- Skips when repeated-region opt-in vars are not provided.

Safety/privacy expectations:

- Metadata validation only by default (no interaction/click behavior in this test).
- No WebView context switching.
- No raw XML/page-source/screenshot bytes/provider payload/capabilities/credentials leakage in diagnostics or report artifacts.
- Meaningful validation requires an app screen that actually contains repeated cards/lists/rows.

## Android Icon Detection Smoke (Phase 19N-Q)

This smoke is Android real-env only and is **skip-by-default**.
It validates safe/compact `icon_detection` metadata generation from a live Appium Android session.

Run command:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_ICON_SMOKE=1 \
BUBBLEGUM_ANDROID_ICON_TARGET=search \
pytest tests/real_env/android/test_android_icon_smoke.py -q
```

Installed app variant:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_PACKAGE=<app-package> \
BUBBLEGUM_ANDROID_ACTIVITY=<launcher-activity> \
BUBBLEGUM_ANDROID_ICON_SMOKE=1 \
BUBBLEGUM_ANDROID_ICON_TARGET=search \
pytest tests/real_env/android/test_android_icon_smoke.py -q
```

Required environment variables:

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_ANDROID_DEVICE_NAME`
- `BUBBLEGUM_ANDROID_APP` **or** (`BUBBLEGUM_ANDROID_PACKAGE` + `BUBBLEGUM_ANDROID_ACTIVITY`)
- `BUBBLEGUM_ANDROID_ICON_SMOKE=1`
- `BUBBLEGUM_ANDROID_ICON_TARGET`

Optional strictness controls:

- `BUBBLEGUM_ANDROID_ICON_EXPECT_STATUS=<status>`
- `BUBBLEGUM_ANDROID_ICON_REQUIRE_RESOLVED=1` (strict resolved-only mode)

Expected skip behavior:

- Skips when real-env is disabled.
- Skips when Android/Appium env vars are missing.
- Skips when icon smoke opt-in vars are missing.
- Skips when Appium runtime/session startup is unavailable.

Safety/privacy expectations:

- Metadata-only validation; no clicks/interactions are performed.
- No `driver.switch_to.context` usage.
- No raw hierarchy payloads, raw capabilities, screenshot bytes, credentials/secrets, raw instruction text, or provider payloads in icon diagnostics.



Android icon detection reporting artifact validation (JSON + HTML under pytest `tmp_path`):

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_ANDROID_DEVICE_NAME=<emulator-name> \
BUBBLEGUM_ANDROID_APP=<path-to-apk> \
BUBBLEGUM_ANDROID_ICON_SMOKE=1 \
BUBBLEGUM_ANDROID_ICON_TARGET=search \
pytest tests/real_env/android/test_android_icon_smoke.py -k reporting_artifacts_are_safe -q
```

Reporting artifact expectations:

- Skips by default unless all required Android/Appium/icon opt-in vars are present.
- Writes one JSON report and one HTML report under pytest `tmp_path` (ephemeral test temp artifacts).
- Validates parseable JSON and presence of `icon_detection_summary` analytics.
- Validates HTML includes `Icon Detection` reporting section content.
- Enforces safety redaction in both artifacts: no raw XML/DOM/hierarchy dumps, screenshots/screenshot bytes, provider payloads, raw context/package/process identifiers, raw candidate fields, raw Appium capability payloads, credentials, or secrets.
- Meaningful validation requires the active app screen to include icon-like UI elements for the requested icon target.

Practical note:

- For meaningful validation, the currently visible app screen should contain icon-like UI elements that match the requested icon target (for example `search`, `delete`, `settings`).

## iOS Simulator Smoke MVP (Phase 19N-V)

This iOS simulator smoke harness is **opt-in** and skip-by-default.
It validates safe Appium iOS context collection and mobile metadata generation only.
No clicking/interaction and no WebView context switching are performed.

### Required environment variables

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_IOS_DEVICE_NAME`
- One of:
  - `BUBBLEGUM_IOS_APP`, or
  - `BUBBLEGUM_IOS_BUNDLE_ID`

### Optional environment variables

- `BUBBLEGUM_IOS_PLATFORM_VERSION`
- `BUBBLEGUM_IOS_AUTOMATION_NAME` (defaults to `XCUITest`)

### iOS simulator smoke command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_IOS_DEVICE_NAME="iPhone 15" \
BUBBLEGUM_IOS_BUNDLE_ID="com.example.myapp" \
pytest tests/real_env/ios/test_ios_simulator_smoke.py -q
```

(Or replace `BUBBLEGUM_IOS_BUNDLE_ID` with `BUBBLEGUM_IOS_APP=/path/to/MyApp.app`.)

### Expected skip behavior

- If `BUBBLEGUM_REAL_ENV` is not `1`, iOS smoke tests skip.
- If required iOS/Appium vars are missing, iOS smoke tests skip with a clear reason.
- If Appium Python client is not installed, tests skip via `pytest.importorskip`.
- If Appium server / simulator runtime is unavailable, tests skip with runtime diagnostics.

### Safety/privacy expectations

The smoke test asserts report-safe metadata behavior and rejects unsafe fields such as:

- `raw_xml`, `raw_dom`, `hierarchy_xml` payload embedding in metadata
- `screenshot_bytes`
- `provider_payload`
- `raw_context_name`
- `package_name`, `process_name`
- `raw_capabilities`
- credential/secret fields

### Runtime prerequisites

You must have a working iOS Appium setup, including:

- Appium server,
- Xcode with iOS Simulator runtime,
- XCUITest-compatible session configuration.

## iOS Simulator Reporting Artifact Validation

These iOS simulator smoke tests are **opt-in** and remain skip-by-default unless explicitly enabled.

### Command

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_IOS_DEVICE_NAME=<simulator-name> \
BUBBLEGUM_IOS_APP=<path-to-ios-app> \
pytest tests/real_env/ios/test_ios_simulator_smoke.py -k reporting -q
```

Bundle-id launch variant:

```bash
BUBBLEGUM_REAL_ENV=1 \
BUBBLEGUM_APPIUM_SERVER_URL=http://127.0.0.1:4723 \
BUBBLEGUM_IOS_DEVICE_NAME=<simulator-name> \
BUBBLEGUM_IOS_BUNDLE_ID=<ios.bundle.id> \
pytest tests/real_env/ios/test_ios_simulator_smoke.py -k reporting -q
```

Optional:

- `BUBBLEGUM_IOS_PLATFORM_VERSION`
- `BUBBLEGUM_IOS_AUTOMATION_NAME` (defaults to `XCUITest`)

### Required env vars

- `BUBBLEGUM_REAL_ENV=1`
- `BUBBLEGUM_APPIUM_SERVER_URL`
- `BUBBLEGUM_IOS_DEVICE_NAME`
- one of:
  - `BUBBLEGUM_IOS_APP`
  - `BUBBLEGUM_IOS_BUNDLE_ID`

### Expected skip behavior

- If `BUBBLEGUM_REAL_ENV` is not `1`, test skips with real-env gating reason.
- If required iOS/Appium vars are missing, test skips with a clear missing-variable list.
- If Appium runtime/session cannot start, test skips with runtime reason.

### Artifact behavior (`tmp_path`)

- Writes one JSON report and one HTML report under pytest `tmp_path`.
- Validates JSON parses and contains report analytics.
- Validates safe iOS mobile metadata sections when present:
  - `framework_detection`
  - `webview_switch_diagnostics`
  - `webview_switch_guardrails`
  - `system_dialog_detection`
  - `system_dialog_guardrails`
  - `scroll_discovery`
  - `mobile_memory_signature` (when safely generated)

### Safety/privacy expectations

- Context/reporting validation only; no interaction/click behavior is required by this test.
- No WebView switching (`driver.switch_to.context`) is performed.
- No raw XML/page source/screenshot bytes/context names/package/process/capabilities/credentials/secrets should be persisted in JSON/HTML artifacts.
- Requires a working Appium server, Xcode iOS simulator runtime, and XCUITest automation setup.
