# RELEASE CHECKLIST — reusable pre-release gates

Historical release note:
- `v0.0.1-alpha` is already released.

Current planning note:
- v0.0.2-alpha planning keeps Playwright and Appium runtime smoke as manual (non-CI-gated).
- Package version target for this cycle: `0.0.2a0` (PEP 440) for GitHub pre-release `v0.0.2-alpha`.

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

Expected baseline for current main:
- benchmark static: 12/12 passed
- benchmark execute: 12/12 passed
- pytest collection: 476 tests collected

## Optional manual Playwright smoke (not CI-gated)

```bash
python -m pip install -e ".[web,test]"
python -m playwright install chromium
python examples/playwright_quickstart.py
```

Notes:
- Keep this as manual smoke for v0.0.2-alpha.
- Do not add runtime Playwright browser execution as required CI gate yet.

## Manual Appium checklist (not CI-gated)

Before running `examples/appium_quickstart.py`, verify:
- Appium server is running (for example `http://localhost:4723`)
- Android/iOS emulator or physical device is connected and available
- target app is installed on the device
- capabilities in `examples/appium_quickstart.py` match local environment

Notes:
- Appium quickstart is intentionally a real-infrastructure template.
- Do not gate CI on mobile runtime infra for v0.0.2-alpha.

## Release policy

- Keep package version aligned to the active release phase.
- For this release cycle, use package version `0.0.2a0` while keeping GitHub tag/title as `v0.0.2-alpha`.
- Use GitHub pre-release tagging per release plan.
- PyPI/TestPyPI publishing remains deferred unless explicitly enabled in a future phase.

## Contributor setup notes for strict/build checks

- `python scripts/validate_package.py` is default-mode and offline-safe.
- Strict mode requires a local editable install so installed distribution metadata is present:
  - `python -m pip install -e ".[test]"`
- Strict/build gates require `build` to be available:
  - `python -m pip install build`


## OCR callable posture for v0.0.2-alpha

- OCR remains callable-only: integrators may supply their own runtime OCR callable backend.
- Screenshot OCR processing stays privacy-gated and opt-in (`process_screenshots_for_ocr: true`).
- No bundled real OCR dependency is required for release readiness.
- OCR resolver refs are synthetic (`ocr://block/<index>`) and are not adapter-executed yet.
