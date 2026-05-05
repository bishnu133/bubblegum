# Bubblegum Examples (Phase 7A)

These examples are **minimal templates** to help you wire Bubblegum into existing automation.

## Requirements

Install Bubblegum core:

```bash
pip install bubblegum-ai
```

Install web prerequisites for Playwright example:

```bash
pip install playwright
playwright install chromium
```

Install mobile prerequisites for Appium example:

```bash
pip install Appium-Python-Client
```

You also need a running Appium server and a connected emulator/device.

## Files

- `playwright_quickstart.py` — async Playwright flow using `recover`, `act`, `verify`, and `extract`.
- `appium_quickstart.py` — Appium flow template using `act` and `verify`.

> These examples intentionally avoid real credentials and should be adapted to your app/test env.
