# RELEASE CHECKLIST — MVP RC (Phase 9B)

Target release tag recommendation: `v0.0.1-alpha`

## Pre-release gates (required)

Run from repository root:

```bash
git status --short
python -m pip install -e ".[test]"
python -m pip install build
python scripts/validate_package.py
python scripts/validate_package.py --strict
python -m build
python scripts/run_benchmarks.py
python scripts/run_benchmarks.py --execute
pytest tests/unit/test_validate_package.py -q
pytest tests/unit/test_package_metadata.py -q
pytest tests/unit/test_packaging_extras.py -q
pytest tests/unit/test_public_api.py -q
pytest --collect-only -q
```

Expected baseline for MVP RC:
- benchmark static: 12/12 passed
- benchmark execute: 12/12 passed
- pytest collection: 445 tests collected

## Optional manual Playwright smoke (not CI-gated)

```bash
python -m pip install -e ".[web,test]"
python -m playwright install chromium
python examples/playwright_quickstart.py
```

Notes:
- Keep this as manual smoke for MVP RC.
- Do not add runtime Playwright browser execution as required CI gate yet.

## Manual Appium checklist (not CI-gated)

Before running `examples/appium_quickstart.py`, verify:
- Appium server is running (for example `http://localhost:4723`)
- Android/iOS emulator or physical device is connected and available
- target app is installed on the device
- capabilities in `examples/appium_quickstart.py` match local environment

Notes:
- Appium quickstart is intentionally a real-infrastructure template.
- Do not gate CI on mobile runtime infra for MVP RC.

## Release policy (MVP RC)

- Keep package version at `0.0.1` for this phase.
- Tag GitHub pre-release as `v0.0.1-alpha` after all required gates pass.
- Do not publish to PyPI/TestPyPI in this phase.
