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

## Quickstart

- `playwright_quickstart.py` — deterministic selector-first local smoke (self-contained HTML).
- `web_nl_quickstart.py` — local natural-language flow (`act` + `verify` + `extract`) with report output.

## Mobile

- `appium_quickstart.py` — Android/Appium template (real infrastructure required).

## Hybrid

- `hybrid_web_mobile_example.py` — selector-first + NL fallback across web/mobile patterns.

## OCR / Vision

- `ocr_callable_hydration_example.py` — deterministic fake OCR callable + hydration metadata pattern.
- `vision_callable_provider_example.py` — callable vision provider lifecycle example.
- `openai_vision_provider_manual_example.py` — optional/manual OpenAI provider setup.

## Reporting

- `report_artifacts_example.py` — writes JSON + HTML reports from sample `StepResult` data.

## Pytest / CI docs

- `../docs/pytest-plugin.md` — pytest flags and sample pattern.
- `../docs/ci.md` — GitHub Actions snippet with artifact upload.

## Infrastructure expectations

- **No external infra required:** `playwright_quickstart.py`, `web_nl_quickstart.py`, `report_artifacts_example.py`, `ocr_callable_hydration_example.py`.
- **Playwright required:** web quickstarts (`.[web]` + browser install).
- **Appium required:** `appium_quickstart.py` and mobile portions of hybrid examples.
- **Optional provider setup:** manual OpenAI example requires user-installed SDK and `OPENAI_API_KEY`.

## Notes

- Examples avoid real credentials.
- OCR/vision synthetic refs are not directly adapter-executable; hydration behavior is deterministic and fail-safe.
