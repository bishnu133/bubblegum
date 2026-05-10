# Bubblegum Examples (Adoption MVP)

These examples are grouped by adoption stage and infrastructure needs.

## Requirements

```bash
# Web examples
pip install -e ".[web]"
python -m playwright install chromium

# Mobile examples
pip install -e ".[mobile]"

# Full optional set
pip install -e ".[all]"
```

## Real Smoke Kit (Phase 17C MVP)

Recommended first-run order:

1. Run infra-free OCR hydration pattern example.
2. Run infra-free report artifact writer example.
3. Run Playwright local NL smoke (after browser setup).
4. Run Appium and OpenAI examples manually only when required infra is ready.

Infra-free commands:

```bash
python examples/ocr_callable_hydration_example.py
python examples/report_artifacts_example.py
```

Playwright local smoke commands:

```bash
python -m pip install -e ".[web]"
python -m playwright install chromium
python examples/web_nl_quickstart.py
```

Manual-only notes:
- Appium/mobile examples require real server/device/app capabilities.
- OpenAI manual vision example requires user-installed `openai`, `OPENAI_API_KEY`, and network for real provider calls.

Expected local artifacts:
- `examples/report_artifacts_example.py` writes:
  - `artifacts/report-artifacts-example.json`
  - `artifacts/report-artifacts-example.html`
- `examples/web_nl_quickstart.py` writes:
  - `artifacts/web-nl-quickstart.json`
  - `artifacts/web-nl-quickstart.html`

These report files are local JSON/HTML outputs intended for safe observability and CI artifact upload.

## Quickstart

- `playwright_quickstart.py` — deterministic selector-first local smoke (self-contained HTML).
- `web_nl_quickstart.py` — local natural-language flow (`act` + `verify` + `extract`) with report output.

Run commands:

```bash
# Prerequisite for web_nl_quickstart.py
pip install -e ".[web]"
python -m playwright install chromium

# Run local natural-language Playwright quickstart
python examples/web_nl_quickstart.py
```

## Mobile

- `appium_quickstart.py` — Android/Appium template (real infrastructure required).

## Hybrid

- `hybrid_web_mobile_example.py` — selector-first + NL fallback across web/mobile patterns.

## OCR / Vision

- `ocr_callable_hydration_example.py` — deterministic fake OCR callable + hydration metadata pattern (no external OCR/provider/network required).
- `vision_callable_provider_example.py` — callable vision provider lifecycle example (infrastructure/manual integration pattern).
- `openai_vision_provider_manual_example.py` — optional/manual OpenAI provider setup (`OPENAI_API_KEY` + user-installed SDK required).

Run commands:

```bash
# No external OCR/provider/network required
python examples/ocr_callable_hydration_example.py
```

## Reporting

- `report_artifacts_example.py` — writes JSON + HTML reports from sample `StepResult` data.

Run commands:

```bash
# No browser/device/provider required
python examples/report_artifacts_example.py
```

## Pytest / CI docs

- `../docs/pytest-plugin.md` — pytest flags and sample pattern.
- `../docs/ci.md` — GitHub Actions snippet with artifact upload.

## Infrastructure expectations

- **No external infra required:** `playwright_quickstart.py`, `web_nl_quickstart.py`, `report_artifacts_example.py`, `ocr_callable_hydration_example.py`.
- **Playwright required:** web quickstarts (`.[web]` + browser install).
- **Appium required:** `appium_quickstart.py` and mobile portions of hybrid examples.
- **Optional provider setup:** manual OpenAI example requires user-installed SDK and `OPENAI_API_KEY`.

## Smoke matrix (infra and CI suitability)

| Example | Command | Requires browser? | Requires device/server? | Requires API key/network? | Output/artifacts | CI suitability |
|---|---|---|---|---|---|---|
| `ocr_callable_hydration_example.py` | `python examples/ocr_callable_hydration_example.py` | No | No | No | Console hydration pattern text | Good for CI/manual |
| `report_artifacts_example.py` | `python examples/report_artifacts_example.py` | No | No | No | `artifacts/report-artifacts-example.{json,html}` | Good for CI/manual |
| `web_nl_quickstart.py` | `python examples/web_nl_quickstart.py` | Yes (Playwright Chromium) | No | No | `artifacts/web-nl-quickstart.{json,html}` | Manual smoke; optional CI |
| `appium_quickstart.py` | `python examples/appium_quickstart.py` | No | Yes (Appium + device/emulator + app) | No | Runtime-specific; optional local artifacts | Manual only |
| `openai_vision_provider_manual_example.py` | `python examples/openai_vision_provider_manual_example.py` | No | No | Yes (`OPENAI_API_KEY` + network for real calls) | Console setup/teardown guidance | Manual only |

## Notes

- Examples avoid real credentials.
- OCR/vision synthetic refs are not directly adapter-executable; hydration behavior is deterministic and fail-safe.
