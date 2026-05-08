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
pytest --collect-only -q  # baseline now 521 tests
```

Expected baseline for current main:
- benchmark static: 12/12 passed
- benchmark execute: 12/12 passed
- pytest collection: 521 tests collected

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


## Vision abstraction posture for Phase 11J

- Vision remains disabled by default and screenshot sharing remains privacy-gated.
- Screenshot-to-vision processing requires explicit opt-in via `process_screenshots_for_vision: true` (default: `false`).
- Phase 11B adds abstraction + deterministic fake backend only (no bundled real vision model dependency).
- Screenshot-to-vision candidate helper is fail-safe and returns empty output on disabled/gated/missing/error states.
- SDK runtime can optionally auto-wire screenshot-to-vision candidate injection, but only when all gates pass (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, provider configured) and remains default-off.

## Phase 11L docs/readiness note

- Callable vision usage/readiness guidance is documented in `docs/phase-11l-callable-vision-enablements.md`.
- Phase 11L introduces no runtime/API/dependency changes; gates and synthetic `vision://` limitations remain unchanged.
- Real OpenAI/Anthropic/Ollama vision provider integrations remain deferred pending provider registration lifecycle finalization.


## Phase 11N lifecycle/reset checks

- Validate `configure_vision_provider(provider)` accepts VisionProvider-compatible objects and rejects invalid providers clearly.
- Validate `clear_vision_provider()` is idempotent and used in test teardown/reset paths.
- Confirm registration/reset do not trigger provider invocation by themselves.
- Confirm privacy/config gates still fully control screenshot-to-vision execution.

## Phase 11P docs/example readiness note

- Public lifecycle example is available at `examples/vision_callable_provider_example.py`.
- Example demonstrates required screenshot-to-vision gates and teardown via `clear_vision_provider()`.
- Example is deterministic/callable-only with no real provider dependency and no raw screenshot-byte logging/persistence guidance violations.


## Phase 11R/11T OpenAI vision backend readiness note

- `OpenAIVisionProvider` coverage is mock-tested only; no real network calls in unit tests.
- No network benchmark fixtures are required for OpenAI vision backend readiness.
- No mandatory OpenAI dependency is introduced in base install.
- Existing vision privacy gates remain unchanged and continue to control screenshot processing.
- Validate Phase 11T hardening behavior:
  - explicit/validated `model` and `timeout` configuration
  - timeout propagation on lazy SDK client construction path
  - response shape parsing for `output_text` and deterministic alternate shapes
  - sanitized fail-safe error paths that do not expose raw screenshot bytes
