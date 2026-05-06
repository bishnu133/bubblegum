# Bubblegum Examples (v0.0.2-alpha planning baseline)

These examples are **minimal templates** to help you wire Bubblegum into existing automation.

## Requirements

Install Bubblegum with extras:

```bash
# Web example (editable install)
pip install -e ".[web]"
python -m playwright install chromium

# Mobile example (editable install)
pip install -e ".[mobile]"

# Or install every optional dependency
pip install -e ".[all]"

# Package-user installs (non-editable)
pip install "bubblegum-ai[web]"
pip install "bubblegum-ai[mobile]"
```

You also need a running Appium server and a connected emulator/device.

## Appium real-environment setup (required)

`appium_quickstart.py` is a real-infrastructure template and is **not self-contained** like the Playwright local HTML smoke.

Before running it:

1. Install mobile dependencies:
   - `pip install -e ".[mobile]"`
   - or `pip install "bubblegum-ai[mobile]"`
2. Start an Appium server (for example `http://localhost:4723`).
3. Start an Android emulator or connect a physical device.
4. Install the target app on the device/emulator (template uses Android ApiDemos).
5. Verify capabilities in `appium_quickstart.py` match your environment:
   - `platformName`
   - `appium:deviceName`
   - `appium:automationName`
   - `appium:appPackage`
   - `appium:appActivity`

## Files

- `playwright_quickstart.py` — async Playwright flow using `recover`, `act`, `verify`, and `extract` with explicit smoke selectors for deterministic first-run checks.
- `appium_quickstart.py` — Appium flow template for real mobile infra (`act` + `verify`).

> These examples intentionally avoid real credentials and should be adapted to your app/test env.


## Troubleshooting

- **Dependency install blocked (proxy/network):** If `pip install -e ".[...]"` fails (for example due to proxy restrictions), configure your proxy/index access first, then retry.
- **Playwright module missing:** Install web deps with `pip install -e ".[web]"` (or `pip install "bubblegum-ai[web]"`).
- **Playwright browser binaries missing:** Run `python -m playwright install chromium`.
- **Appium server/device missing:** Start Appium server, connect an emulator/device, and update capabilities in `appium_quickstart.py` for your local app.
- **Template expectations:** These examples are templates. Target URLs, selectors, app package/activity, and assertions may require local adjustment.

### Appium common failures

- **Appium Python client missing** (`ModuleNotFoundError: appium`):
  - install mobile extra (`pip install -e ".[mobile]"` or `pip install "bubblegum-ai[mobile]"`).
- **Appium server not running / wrong URL**:
  - start server and confirm URL in template (default `http://localhost:4723`).
- **Device/emulator not visible**:
  - start emulator or connect device and verify it is available to Appium.
- **`appPackage` / `appActivity` mismatch**:
  - align capabilities with the installed app entry activity/package.
- **App not installed**:
  - install target app on device/emulator before quickstart run.

### Quick expectations

- `playwright_quickstart.py` uses `page.set_content(...)` with deterministic local HTML by default, so smoke validation does not require outbound network access. The built-in smoke path uses explicit selectors to make first-run `act` / `verify` / `extract` deterministic. After this path works, adapt it to your real web target (URL/selectors/assertions) and try natural-language-only prompts. The `recover()` block is demonstrative and may require a real app/stale selector to produce a meaningful recovery.
- `appium_quickstart.py` requires real mobile infrastructure: running Appium server, running emulator/device, and an installed target app (ApiDemos in the template). It is not self-contained like the Playwright local HTML smoke.
