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

## PR 3 — Strong AI-first object recognition ✅
- New **Claude vision backend** (`bubblegum/core/vision/backends/anthropic.py`): real
  screenshot → `messages.create` (image block) → JSON candidates →
  normalized `VisionCandidate`s. Default `claude-opus-4-8` (high-res, 1:1 pixel
  coordinates), injectable client for tests, fail-safe with sanitized diagnostics.
  OpenAI/callable backends and the injectable interface stay intact (provider-neutral seam).
- The screenshot→provider→candidate pipeline was already wired in the SDK
  (`_maybe_build_vision_candidates` → `build_vision_candidates_from_screenshot`);
  PR3 supplies the Claude provider that plugs into it via `configure_vision_provider()`.
- Added an **AI-first** resolution strategy (`grounding.ai_first`) so the AI tier runs
  before the deterministic tiers when opted in. It only reorders when the AI tier can
  actually run (cost policy permits + an eligible Tier 3 resolver exists), so it never
  blocks deterministic resolution and keeps the traceable fallback chain.
- `max_cost_level` continues to gate provider vision (only runs at `high`), so AI-first
  can't trigger unbounded paid calls.

  Follow-up (not blocking): add a vision-grounding regression fixture to the
  widget-lab harness once a screenshot corpus is available.

## PR 4 — PyPI packaging (v0.0.5a) ✅
- The `widget_lab` and `sample_app` quickstart pages now ship inside the package
  (`bubblegum/testing/pages/`) and are included in the wheel via
  `[tool.setuptools.package-data]`, so pip-installed users get the fixtures without a
  repo checkout.
- `find_pages_dir()` resolves a repo checkout first (dev), then falls back to the bundled
  copies (pip install). A drift guard test keeps the two byte-for-byte in sync.
- `python -m build` produces a wheel containing all 14 sample pages; `validate_package.py`
  (default + strict) passes.

  Follow-up (not blocking): actual upload to PyPI / TestPyPI via `publish-check.yml` is a
  release-time action, not a code change.

## PR 5 — BDD step library ✅
- New `bubblegum.bdd` package. The core is a framework-agnostic async dispatcher
  (`execute_step(session, text)`) that maps plain-English Gherkin steps onto a
  BubblegumSession (`act / goto / is_visible / is_checked / selected_value / extract`) —
  fully unit-tested without a browser or BDD runner (20 tests).
- `bubblegum.bdd.steps` provides catch-all pytest-bdd **When/Then** bindings (Given is
  left to the project so custom setup steps never collide). Optional dependency:
  `pip install "bubblegum-ai[bdd]"` (pytest-bdd >= 7).
- Self-healed steps (status `recovered`) pass and surface the healing advisory; failed
  steps raise a `BddStepError`. Added a runnable example (`examples/web/bdd/`) + runbook.

## PR 6 — Nameless-combobox resolver fallback ✅
- A dropdown/combobox trigger with no accessible name (MUI / Angular CDK overlays) scored
  only 0.60 in the accessibility-tree resolver — below the 0.70 review band — so it was
  dropped and the step failed. When the instruction signals a dropdown (combobox/select/
  dropdown kind hint, or a `select` action) and exactly one nameless combobox/listbox is
  present, it is now lifted into the review band and resolves by role + uniqueness.
- Named comboboxes still outrank the fallback; multiple nameless comboboxes stay ambiguous
  (no false grab). Added a real `nameless_combobox.html` widget-lab page (bundled), an
  opt-in `--playwright` web smoke, and 7 unit tests covering the resolver + engine paths.
