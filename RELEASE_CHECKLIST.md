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
rm -rf dist build *.egg-info  # avoids stale artifacts from prior builds
python -m build
python scripts/run_benchmarks.py
python scripts/run_benchmarks.py --execute
python -m py_compile examples/openai_vision_provider_manual_example.py
pytest tests/unit/test_phase11j_sdk_vision_wiring.py -q
pytest tests/unit/test_phase11n_vision_provider_registration.py -q
pytest tests/unit/test_phase11r_openai_vision_provider.py -q
pytest tests/unit/test_phase11x_openai_vision_diagnostics.py -q
pytest tests/unit/test_public_api.py -q
pytest tests/unit/test_packaging_extras.py -q
pytest tests/unit/test_package_metadata.py -q
pytest --collect-only -q  # baseline now 567 tests
```

Expected baseline for current main:
- benchmark static: 12/12 passed
- benchmark execute: 12/12 passed
- pytest collection: 567 tests collected

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


## Vision/OCR limitations and gating posture for v0.0.2-alpha

- Vision remains disabled by default and screenshot sharing remains privacy-gated.
- Screenshot-to-vision processing requires explicit opt-in via `process_screenshots_for_vision: true` (default: `false`).
- Phase 11B adds abstraction + deterministic fake backend only (no bundled real vision model dependency).
- Screenshot-to-vision candidate helper is fail-safe and returns empty output on disabled/gated/missing/error states.
- SDK runtime can optionally auto-wire screenshot-to-vision candidate injection, but only when all gates pass (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, provider configured) and remains default-off.
- Vision resolver refs are synthetic (`vision://target/<index>`) and are non-executable placeholders.
- Phase 13G introduces a VisualRefHydrator SDK boundary so synthetic visual refs are never sent directly to adapters unless deterministically hydrated.
- No bbox center-click fallback is enabled by default; unsupported visual-ref hydration fails safe.
- Provider-based screenshot vision additionally requires `max_cost_level: high`; low/medium cost levels fail-safe skip provider invocation.

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


## Phase 11V manual OpenAI vision docs/example readiness note

- Manual optional example is available at `examples/openai_vision_provider_manual_example.py`.
- Example is import-safe, does not execute network calls on import, and is not part of test/benchmark execution.
- OpenAI SDK remains user-installed (`python -m pip install openai`); no dependency extras are introduced in this phase.
- Usage requires `OPENAI_API_KEY`, explicit provider registration, all screenshot/vision privacy gates, and teardown via `clear_vision_provider()`.
- No runtime/API/adapter/resolver/dependency/version changes are required for this docs/example slice.



## Phase 11Z cost-gating checks

- Validate screenshot-to-vision provider invocation requires `max_cost_level: high` plus all existing vision/privacy/provider gates.
- Validate low/medium cost levels skip provider invocation and skip screenshot request when screenshot is only needed for provider vision.
- Validate manual `vision_candidates` stay allowed and are not overwritten/blocked by cost gating.

## Phase 11X diagnostics hardening checks

- Validate OpenAIVisionProvider exposes sanitized diagnostics via `last_diagnostic` / `get_last_diagnostic()`.
- Validate success path clears diagnostics (`None`).
- Validate fail-safe `[]` behavior remains unchanged for empty input/client init/request/parse failures.
- Validate diagnostics never include raw screenshot bytes, base64 payloads, API keys/secrets, full request payloads, or raw provider response bodies.


## Phase 12B docs/example readiness note

- Manual OpenAI example (`examples/openai_vision_provider_manual_example.py`) is API-correct: `configure_runtime(config=BubblegumConfig.model_validate(...))` and no unsupported `api_key=` constructor arg.
- `python -m py_compile examples/openai_vision_provider_manual_example.py` remains a required safety check.
- OpenAI SDK remains user-installed and reads `OPENAI_API_KEY` from environment; no mandatory OpenAI dependency is introduced.
- Provider-based screenshot-to-vision still requires `max_cost_level: high` plus existing vision/privacy/provider gates.
- No runtime/API/adapter/resolver/dependency/version changes in this phase.


## Phase 13C publish-readiness posture (no publishing)

- Phase 13C adds a manual-only GitHub Actions readiness workflow: `.github/workflows/publish-check.yml`.
- Workflow trigger is `workflow_dispatch` only.
- Publishing to TestPyPI/PyPI remains deferred in this phase.
- No publish credentials/secrets are configured in the workflow.
- `pypa/gh-action-pypi-publish` is intentionally not used yet.

Expected publish-readiness commands:

```bash
python -m build
python -m twine check dist/*
pytest --collect-only -q  # baseline remains 557 tests
```

Policy notes:
- Prefer trusted publishing (GitHub OIDC) in a later explicit publishing phase.
- Avoid manual token-based publishing wherever possible.
- Actual TestPyPI publish requires a separate, explicit future phase.


## Phase 13I deterministic hydration checks

- Phase 13I adds deterministic web-only visual-ref hydration in SDK boundary via `VisualRefHydrator`.
- OCR synthetic refs may hydrate to executable web text refs when text metadata is present.
- Vision synthetic refs may hydrate to executable web role+name or text refs when deterministic metadata is present.
- Mobile visual hydration remains fail-safe/deferred.
- No bbox proximity or center-click fallback is enabled.
- Phase 13K extends deterministic mobile hydration via hierarchy XML exact matching (`text` -> `content-desc` -> `resource-id`) with stable fail-safe reasons for no hierarchy/invalid hierarchy/no-match/ambiguous/unsupported metadata.
