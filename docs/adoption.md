# Adoption Guide (Phase 14C MVP)

This guide defines a **fallback-first** rollout for Bubblegum `0.0.3a0` with GitHub pre-release tag `v0.0.3-alpha`.

## 1) Recommended rollout ladder

1. **Fallback-first (recommended start):** keep existing selectors and add `recover(...)` around flaky steps.
2. **Hybrid adoption:** mix explicit selectors for critical flows and natural-language `act`/`verify`/`extract` for resilience.
3. **Direct NL execution:** write higher-level intent-first flows once confidence and observability are established.

## 2) Fallback-first adoption

Use Bubblegum first as a healing layer on top of existing Playwright/Appium tests.

- Keep deterministic selectors as your primary path.
- Add natural-language context (`intent`) for recovery.
- Capture HTML/JSON reports on CI so teams can review why a step passed, recovered, or failed.

See: `examples/playwright_quickstart.py`, `examples/appium_quickstart.py`, and `examples/report_artifacts_example.py`.

## 3) Hybrid adoption

Hybrid mode combines low-risk selectors with NL fallback:

- critical compliance steps: explicit selectors/assertions
- high-change UI areas: `act(...)` / `extract(...)` natural-language hints
- triage path: report analytics + hydration diagnostics

See: `examples/hybrid_web_mobile_example.py`.

## 4) Direct natural-language mode

Use direct NL mode after fallback/hybrid prove stable for your app:

- keep deterministic-first principles where possible, while allowing configured fallback tiers
- understand that resolver/fallback paths depend on runtime config, cost level, provider setup, and privacy gates
- keep report artifact generation on every pipeline run for observability
- gate cost-sensitive provider flows with explicit config and privacy controls

See: `examples/web_nl_quickstart.py`.

## 5) Choosing web/mobile/vision/OCR

- **Web (Playwright):** local smoke, browser automation, selector + NL flows.
- **Mobile (Appium):** real device/emulator workflows with capabilities.
- **OCR:** when text is present in screenshots or visual regions and selector data is missing.
- **Vision:** when semantic target identification from screenshots is needed.

For OCR/vision callable patterns, see:
- `examples/ocr_callable_hydration_example.py`
- `examples/vision_callable_provider_example.py`
- `examples/openai_vision_provider_manual_example.py` (manual/optional)

## 6) Safety and privacy posture

Default posture remains conservative:

- screenshot processing is opt-in
- vision processing is opt-in
- no raw screenshot/base64 payload persistence in reports
- hydration diagnostics are sanitized for report safety

Always review `bubblegum.yaml` privacy and grounding settings before enabling screenshot-based flows.

## 7) Start with reports early

Generate report artifacts from day one:

```bash
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-artifacts artifacts \
  --bubblegum-report artifacts/bubblegum-report.html \
  --bubblegum-report-json artifacts/bubblegum-report.json
```

For non-pytest usage, see `examples/report_artifacts_example.py`.

## 8) Deferred from this track (v0.0.4-alpha planning)

This adoption/docs track intentionally defers:

- waits/retries runtime behavior changes
- policy engine work
- provider expansion
- Selenium adapter
- iOS maturity work
- TestPyPI/PyPI publishing

These remain separate follow-on tracks after adoption examples and smoke-kit docs are stable.
