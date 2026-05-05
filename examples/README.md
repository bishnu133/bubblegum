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
