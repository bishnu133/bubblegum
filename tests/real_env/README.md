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
- `BUBBLEGUM_ANDROID_APP` — required for Android target smoke skeleton.
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
