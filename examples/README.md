# Bubblegum Examples (Phase 7A)

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

## Files

- `playwright_quickstart.py` — async Playwright flow using `recover`, `act`, `verify`, and `extract`.
- `appium_quickstart.py` — Appium flow template using `act` and `verify`.

> These examples intentionally avoid real credentials and should be adapted to your app/test env.


## Troubleshooting

- **Dependency install blocked (proxy/network):** If `pip install -e ".[...]"` fails (for example due to proxy restrictions), configure your proxy/index access first, then retry.
- **Playwright module missing:** Install web deps with `pip install -e ".[web]"` (or `pip install "bubblegum-ai[web]"`).
- **Playwright browser binaries missing:** Run `python -m playwright install chromium`.
- **Appium server/device missing:** Start Appium server, connect an emulator/device, and update capabilities in `appium_quickstart.py` for your local app.
- **Template expectations:** These examples are templates. Target URLs, selectors, app package/activity, and assertions may require local adjustment.

### Quick expectations

- `playwright_quickstart.py` should run after web dependencies + Chromium are installed. The `recover()` block is demonstrative and may require a real app/stale selector to produce a meaningful recovery.
- `appium_quickstart.py` requires a real Appium session (server + device/emulator + compatible capabilities).
