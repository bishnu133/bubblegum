# Bubblegum Roadmap

This is the working plan we are executing, in order. Each item is a self-contained PR.

## PR 1 — Real CI + baseline test cleanup ✅ (this PR)
- Fixed the 17 stale "documented baseline" unit failures:
  - `test_anthropic_provider.py` / `test_phase2.py` — gated on `pytest.importorskip("anthropic")`.
  - `test_phase15f_playwright_wait.py` / `test_phase15b_playwright_retry.py` — `_FakePage`
    gained the `url` attribute + `wait_for_url()` the navigation-detection path now uses.
  - `test_phase1b.py` extract mocks — wired `locator.first` (the extract path reads via
    `locator.first.inner_text()`).
- Added a `unit-tests` CI job that installs `.[test,anthropic]` and runs the full
  `pytest` suite on every PR, so green means green.

## PR 2 — Self-healing defect advisory
When a step is resolved by a non-exact / synonym / fuzzy match (e.g. tester wrote
"click login" but the app only has a "Sign In" button), Bubblegum should not silently
heal it. It should:
- Set `StepResult.status = "recovered"` on the natural-language `act()` path (the status
  already exists but is currently only set by the explicit-selector `recover()` path).
- Attach a structured `healing` advisory (requested phrase, matched label, resolver,
  match kind, similarity, severity).
- Surface it prominently in the HTML/JSON reports with a "review this step — it may be a
  real defect" callout, plus a per-run count of auto-healed steps.
- Thresholds configurable (synonym hits always flag; fuzzy flags below a similarity cutoff).

## PR 3 — Strong AI-first object recognition
- New **Claude vision backend** (`bubblegum/core/vision/backends/anthropic.py`): real
  screenshot → `messages.create` (image block + structured-output JSON schema for
  bboxes/labels/roles) → normalized `VisionCandidate`s. Default `claude-opus-4-8`
  (high-res, 1:1 pixel coordinates), configurable; provider injectable for tests.
  OpenAI/callable backends and the injectable interface stay intact (provider-neutral seam).
- Wire `VisionModelResolver` to actually capture a screenshot and call the backend
  (today it only consumes injected candidates).
- Add an **AI-first** resolution strategy flag so the vision/LLM tier can run before the
  deterministic tiers when opted in, without losing the traceable fallback chain.
- Honor `max_cost_level` so AI-first can't run unbounded paid calls in CI.
- Add a vision-grounding regression fixture to the widget-lab harness.

## PR 4 — PyPI packaging (v0.0.5a)
- Ship the sample pages (`sample_app` / `widget_lab`) inside the package so pip-installed
  users get the quickstart without a repo checkout.
- Build/validate/publish dry-run via `publish-check.yml`.

## PR 5 — BDD step library
- pytest-bdd / behave Given/When/Then wrappers over the NL engine for manual-QA personas.

## PR 6 — Nameless-combobox resolver fallback
- Small queued resolver follow-up; can ride along with any PR.
