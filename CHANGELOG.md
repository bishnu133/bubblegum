# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Planned for v0.0.2-alpha
- Appium onboarding documentation improvements across README and examples.
- Manual mobile smoke guidance clarified (Appium runtime smoke remains manual and non-CI-gated).
- Release checklist consistency cleanup for reusable pre-release gates.
- OCRResolver injected-block MVP added (context-driven `ocr_blocks`, deterministic synthetic refs `ocr://block/<index>`, no external OCR engine dependency yet).
- Phase 10J planning documentation added for post-OCR MVP verification, risk assessment, and next-slice recommendation (Phase 10K hybrid web + mobile examples).

## v0.0.1-alpha (MVP RC)

### Highlights
- Playwright explicit-selector quickstart path is in place for deterministic first-run smoke usage.
- Playwright natural-language `act`, `verify`, and `extract` usage paths are available for MVP workflows.
- Mobile channel routing supports `act`, `verify`, and `extract` via Appium adapter wiring.
- Appium quickstart is provided as a real-infrastructure template (server/device/app/capability aligned environment).
- Deterministic benchmark baselines are passing:
  - Static validation: 12/12
  - Execute validation: 12/12

### Known limitations
- Appium quickstart requires real mobile infrastructure:
  - running Appium server
  - running emulator/device
  - installed target app
  - local capability alignment
- Playwright quickstart is deterministic local smoke (`page.set_content(...)`) and is not full real-app coverage.
- Tier 3 AI/LLM/vision/ocr behavior remains optional and depends on explicit configuration, provider setup, and environment.
- PyPI/TestPyPI publishing is deferred for this MVP RC; release target is GitHub pre-release tagging.
