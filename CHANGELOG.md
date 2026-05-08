# Changelog

All notable changes to this project will be documented in this file.

## Unreleased
- Phase 11H vision privacy/config contract hardening: added `privacy.process_screenshots_for_vision` (default `false`) to make screenshot-to-vision processing an explicit opt-in flag. No SDK runtime auto-wiring was added; resolver behavior remains injected-candidate-only and `vision://` refs remain synthetic/non-executable.
- Phase 11F user-supplied vision callable backend added (`bubblegum/core/vision/backends/callable.py`) via `CallableVisionProvider`, enabling runtime-provided vision candidate callables to feed the existing normalized screenshot vision pipeline (still opt-in/privacy-gated, no bundled real vision model dependency).
- Phase 11D VisionModelResolver injected-candidate MVP implemented: resolver now consumes `intent.context["vision_candidates"]`, normalizes via existing vision engine helpers, emits synthetic `vision://target/<index>` candidates with ranker-compatible signals/metadata, and suppresses weak unrelated matches. No real vision provider/model dependency or adapter-executable vision refs added.
- Phase 11B vision abstraction scaffold added (`bubblegum/core/vision/engine.py`): `VisionCandidate`, `VisionProvider` protocol, deterministic `FakeVisionProvider`, candidate normalization, and safe screenshot-to-vision pipeline helper (mock/fake only; no bundled real vision model dependency).

## v0.0.2-alpha
- Phase 10Q release/docs readiness cleanup completed: release checklist collect-only baseline synced to 476, and OCR callable-only contract/privacy gate/synthetic `ocr://` ref limitation documented for v0.0.2-alpha readiness.
- Appium onboarding documentation improvements across README and examples.
- Manual mobile smoke guidance clarified (Appium runtime smoke remains manual and non-CI-gated).
- Release checklist consistency cleanup for reusable pre-release gates.
- OCRResolver injected-block MVP added (context-driven `ocr_blocks`, deterministic synthetic refs `ocr://block/<index>`, no external OCR engine dependency yet).
- Phase 10J planning documentation added for post-OCR MVP verification, risk assessment, and next-slice recommendation (Phase 10K hybrid web + mobile examples).
- Phase 10K hybrid web + mobile examples added (`examples/hybrid_web_mobile_example.py`) with README linkage and guidance (docs/examples only; no runtime behavior changes).
- Phase 10M OCR engine abstraction added (`bubblegum/core/ocr/engine.py`) with deterministic fake engine, OCR block normalization, and mocked screenshot-to-block pipeline helper (no external OCR dependency, no adapter/runtime behavior changes).
- Phase 10O user-supplied OCR callable backend added (`bubblegum/core/ocr/backends/callable.py`) via `CallableOCREngine`, enabling runtime-provided OCR functions to feed the existing normalized screenshot OCR pipeline (still opt-in, no bundled real OCR dependency).
- PyPI/TestPyPI publishing remains deferred; release target continues to be GitHub pre-release tagging for `v0.0.2-alpha`.

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
