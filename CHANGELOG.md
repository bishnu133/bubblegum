# Unreleased

## Web reliability: iframes, bounded nav-wait, select-by-label, strict-mode + re-grounding

Five web-channel improvements to the Playwright adapter and SDK resolution loop:

- **iframe support.** `collect_context()` now merges child-frame accessibility
  snapshots, so elements inside same-origin `<iframe>`s are discoverable by the
  resolvers. Execution and text extraction route into the owning frame
  (`_resolve_action_locator`). Gated by `ContextRequest.include_frames`
  (default on); a no-op for frameless pages.
- **Bounded, configurable post-click navigation wait.** A non-navigating
  (AJAX/SPA) click previously burned a fixed 5 s on the `wait_for_url` probe.
  It is now two-phase — cheaply detect whether a navigation commits within
  `ExecutionOptions.nav_wait_ms` (default 1 s), and only then wait for the new
  document to settle using the full action timeout. Set `nav_wait_ms=0` to skip.
- **`<select>` by visible label.** `select` now tries the option value, then
  falls back to the visible label, so `Select "United States" from Country`
  works even when the option value differs (`value="US"`).
- **Strict-mode retry.** An action whose ref matches more than one DOM node
  retries on `.first` (mirroring the read path) instead of failing the step.
- **Re-grounding for late-rendered elements.** `act()/verify()/extract()`
  re-collect context and retry resolution (`grounding.resolve_retries`,
  default 2 × `resolve_retry_interval_ms` 300 ms) when the first attempt finds
  nothing, so SPA elements that render a beat late resolve instead of failing.

Web text extraction now delegates to `PlaywrightAdapter.extract_text()` (parity
with the mobile channel). New fixtures: `widget_lab/iframe.html` +
`iframe_inner.html`. Coverage: `tests/unit/test_web_resilience.py` (browser-free)
and `tests/integration/test_phase22e10_web_resilience_e2e.py` (live, `--playwright`).

## Self-healing advisory survives memory-cache replays

- A self-healing substitution (e.g. a step written for "login" that resolves to
  "Sign In") was flagged on the first run but went silent on every subsequent
  run, because the step then replayed from the memory cache (`memory_cache`
  resolver) rather than `fuzzy_text`. The advisory is now built **before** the
  resolution is persisted, so it is stored in the cached metadata and
  re-surfaced on replay (tagged `replayed_from_cache`). A replayed healed step
  stays `recovered` instead of being silently downgraded to `passed`.
  Coverage: `tests/unit/test_self_healing_advisory.py`.

## Vision tier validation on deterministic-hard targets

- Added `tests/unit/test_vision_deterministic_hard.py`: proves the AI (vision)
  tier wins grounding on an icon/image control with **no** accessible name (where
  the text/role resolvers cannot match), that it does **not** displace a clean
  deterministic match, and that the same target fails to resolve when vision is
  unavailable or cost-blocked. No API key required (candidates are injected
  exactly as the screenshot→provider pipeline injects them).
- Note: web *execution* of a vision win still relies on the deterministic
  hydrator mapping the candidate to a role/text ref — coordinate (bbox) clicking
  for truly nameless controls remains a future enhancement.

## Mobile re-grounding parity

- The SDK re-grounding loop is channel-agnostic, so the late-render retry now
  benefits mobile too. Coverage: `tests/unit/test_mobile_reground.py` (fake
  Appium adapter; full on-device e2e runs via the env-gated
  `tests/real_env/android|ios` suites).

## BDD step library + nameless-combobox fallback

- Added `bubblegum.bdd`: plain-English Given/When/Then on top of the NL engine
  for manual-QA personas. Core is a framework-agnostic dispatcher
  (`execute_step`); `bubblegum.bdd.steps` ships catch-all pytest-bdd When/Then
  bindings (optional extra `bdd` = `pytest-bdd>=7`). Runnable example under
  `examples/web/bdd/`.
- Nameless-combobox resolver fallback: a `role="combobox"` trigger with no
  accessible name (MUI / Angular CDK overlays) now resolves by role + uniqueness
  when the step signals a dropdown, instead of failing below the review band.

## Packaging: bundle quickstart sample pages (v0.0.5a)

- The `widget_lab` and `sample_app` quickstart pages now ship **inside** the
  package (`bubblegum/testing/pages/`), so `pip install bubblegum-ai` users get
  the fixtures without a repository checkout. `find_pages_dir()` resolves a repo
  checkout first (dev) and falls back to the bundled copies (pip install).
- Added `[tool.setuptools.package-data]` so the HTML pages are included in the
  wheel, and a drift guard (`tests/unit/test_packaged_sample_pages.py`) that
  keeps the bundled copies byte-for-byte in sync with the example sources.

## CI + self-healing + AI-first object recognition

- CI now runs the full unit suite on every PR (`.[test,anthropic]`); fixed the
  17 stale baseline test failures so the gate is meaningful.
- Self-healing is no longer silent: a fuzzy/synonym substitution (e.g. a step
  written for "login" that resolves to "Sign In") marks the step `recovered`,
  attaches a `healing` advisory, and is highlighted in the HTML/JSON reports as
  a possible defect to revisit.
- Added an Anthropic (Claude) vision backend for element grounding from
  screenshots and an opt-in `grounding.ai_first` strategy that runs the AI tier
  before the deterministic tiers (cost-gated, with deterministic fallback).

## Phase 19G-E1 (release checklist baseline sync)

- Phase 19G-E1 docs/checklist-only cleanup: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match the current mainline pytest collection baseline. No runtime/parser/planner/schema/resolver/ranker/confidence/API/dependency/version changes.

## Phase 19F-F (Object Intelligence static summary/reporting MVP)

- Added compact static summary/reporting for Object Intelligence seed fixtures when selected via
  `python scripts/run_benchmarks.py --cases tests/benchmarks/object_intelligence/seed_cases.json`.
- Summary includes deterministic counts for total cases, channel, category, positive vs negative,
  failure modes, baseline expectations, expected graph-signal true counts, relation types, and tags.
- Execution remains intentionally unsupported for object seed fixture shape under `--execute`, with
  clear nonzero operator message unchanged.
- Default regression benchmark behavior remains unchanged when `--cases` is omitted.

## Phase 19F-D (minimal benchmark runner case-path selection)

- Added non-breaking optional benchmark runner case selection via
  `python scripts/run_benchmarks.py --cases <path>`.
- Default behavior remains unchanged: omitting `--cases` still runs regression fixtures from
  `tests/benchmarks/fixtures/cases.json` with existing static/execute behavior.
- Added safe validation-only support for non-regression fixture shapes (including Object
  Intelligence seed fixture format with top-level `{"cases": [...]}`); these can be loaded in
  static mode and report a clear unsupported message in `--execute` mode.
- Added unit coverage for explicit default fixture path parity, object seed opt-in validation path,
  non-supported execute path behavior, and clear invalid-path failure.

## Phase 19F-B (Object Intelligence benchmark seed fixtures MVP)

- Added Object Intelligence seed spec doc at
  `docs/phase-19f-object-intelligence-seed-spec.md`.
- Added separate Object Intelligence seed fixtures at
  `tests/benchmarks/object_intelligence/seed_cases.json`.
- Added dedicated Object Intelligence seed schema at
  `tests/benchmarks/object_intelligence/schema.json`.
- Added unit validation for seed/schema shape and safety checks at
  `tests/unit/test_object_intelligence_seed_schema.py`.
- Scope is docs/fixtures/schema-validation only; no runner runtime logic, scoring,
  resolver priority, or engine behavior changes in this phase.

# Changelog

- Phase 19E-B metadata-only graph diagnostics MVP: added internal `graph_signals` helper to compute compact, deterministic, JSON-safe graph-context diagnostics (`label_for_match`, `same_row_match`, `same_container_match`, `nearby_label_match`, `role_match_with_graph_context`, `unique_in_scope`, `visible_enabled_match`) and emitted these under `metadata["graph_signals"]` in AccessibilityTreeResolver and AppiumHierarchyResolver candidates. No engine/ranker/confidence/threshold changes, no resolver priority/order changes, no SDK/API/schema/dependency/version changes, and no adapter runtime behavior changes.
- Phase 19E-D graph signal reporting/analytics MVP: report surfaces now preserve sanitized `metadata["graph_signals"]` in JSON output, redact unsafe graph diagnostic payload keys, render an optional compact per-step “Graph Signals” section in HTML reports, and add aggregate `graph_signal_summary` analytics (`total_events`, `presence_counts`, `reason_counts`, `field_true_counts`). Reporting-only scope; no scoring/ranker/confidence/engine/resolver/API/schema/dependency/version changes.

All notable changes to this project will be documented in this file.

## Unreleased
- Phase 19G-O object seed diagnostic runner MVP: added opt-in metadata-only script `scripts/run_object_seed_diagnostics.py` that loads object seed cases + synthetic element sidecar, parses relational intent via existing parser helper, builds `NormalizedElement`/`ElementGraph`, runs `build_graph_query_diagnostics(...)`, and emits compact summary counts with optional compact JSON artifact output. Added synthetic sidecar fixture `tests/benchmarks/object_intelligence/synthetic_elements.json` and focused unit coverage in `tests/unit/test_phase19g_object_seed_diagnostics_runner.py`. No action execution, no resolver/ranker/scoring/filtering/runtime targeting changes, no default benchmark behavior changes, no SDK/API/schema/dependency/version changes.
- Phase 19G-L graph query diagnostics reporting/analytics support: JSON reports now preserve sanitized `metadata["graph_query_diagnostics"]` (safe compact keys only), HTML reports render optional escaped "Graph Query Diagnostics" step sections only when present, and reporting analytics include compact `graph_query_summary` aggregates (`total_events`, `status_counts`, `relation_type_counts`, `ambiguity_count`, `reason_counts`, `matched_id_total`) derived from sanitized diagnostics only. Reporting-only scope; no resolver/query/parser/planner/schema/ranker/confidence/engine/API/dependency/version changes.
- Phase 19G-K resolver metadata-only graph query diagnostics integration: AccessibilityTreeResolver and AppiumHierarchyResolver now attach internal `metadata["graph_query_diagnostics"]` when both relational intent and an ElementGraph context (`element_graph` or `graph`) are available. Diagnostics are produced by existing `build_graph_query_diagnostics(...)` and remain metadata-only (no candidate filtering, no scoring/confidence changes, no resolver priority/order changes, no engine/parser/planner/schema/API/dependency/version changes).
- Phase 19G-I metadata-only graph query diagnostics MVP: added internal `build_graph_query_diagnostics(...)` in `bubblegum/core/elements/query.py` to map `relational_intent` into deterministic, compact, JSON-safe graph-query diagnostics (`status`, `relation_type`, `anchor_resolution`, `scope_resolution`, `matched_ids`, `excluded_ids`, `ambiguity`, `reasons`) across `label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, and `mobile_attr_hint`. Diagnostics-only scope: no runtime candidate filtering/selection, no engine/resolver/ranker/confidence changes, no parser/planner/schema/API/dependency/version changes.
- Phase 19G-G graph query planner design/spec added (`docs/phase-19g-graph-query-planner-design.md`): defines deterministic `relational_intent`→ElementGraph diagnostics mapping, fail-closed ambiguity/status model, container-detection heuristics, JSON-safe diagnostics contract, and phased integration path (diagnostics-first; runtime filtering/scoring deferred). Docs-only; no runtime/parser/planner/schema/resolver/ranker/engine/API/dependency/version changes.
- Phase 19G-E1 docs/checklist baseline sync: updated `RELEASE_CHECKLIST.md` collect-only baseline references from 643 to 654 to match current mainline test collection. Docs/checklist-only change; no runtime/parser/planner/schema/resolver/ranker/API/dependency/version changes.
- Phase 19G-D parser relational metadata MVP: added internal rule-based `parse_relational_intent(...)` helper for safe relational hints (`for <anchor>`, modal scope phrases, dropdown scope phrases, checkbox label phrases) and metadata-only planner propagation into `StepIntent.context["relational_intent"]` when matched. No resolver/engine/ranker/confidence/schema/API/dependency/version changes; no runtime targeting behavior changes.

- Phase 19G-B relational intent contract design/spec added (`docs/phase-19g-relational-intent-design.md`): defines schema-stable `StepIntent.context["relational_intent"]` metadata proposal, initial relation taxonomy (`label_for`, `same_row_as_text`, `within_card`, `within_modal`, `within_region`, `mobile_attr_hint`), conservative parser principles, backward-compat strategy, pre-implementation test gates, and phased follow-on plan. Design-only: no parser/planner/runtime/ranker/schema/API/dependency/version changes.

- Phase 19C Normalized Cross-platform Element Model MVP added internal-only normalized element contracts in `bubblegum/core/elements/normalized.py` (`NormalizedElement`, `NormalizedBounds`) plus deterministic web/mobile normalization helpers and JSON-safe serialization. Added focused unit coverage for defaults, serialization safety, web/mobile mapping, bounds parsing/clamping, and parent/child linkage. No runtime resolver/ranker/adapter behavior changes, no SDK public API changes, no dependency/version changes.

- Phase 19B Object Intelligence Benchmark and Regression Design docs added (`docs/phase-19b-object-intelligence-benchmark.md`), explicitly separating capability benchmarking from regression protection. Defines benchmark taxonomy (web/mobile), baseline comparison strategy (raw Playwright, raw vision/LLM grounding, current Bubblegum pipeline), required metrics/failure taxonomy, ground-truth case format, fixture scale targets, mobile-specific design track (FrameworkDetector/WebView/SystemDialog/IconLibrary/screen signatures), roadmap reorder through 19M, and explicit deferrals (no multilingual claim yet, no full device-cloud matrix, no Selenium adapter in this phase). Docs/design-only scope; no runtime/API/schema/dependency/version changes.

- Phase 15H wait observability metadata/reporting MVP: adapter execute paths now emit safe wait metadata on existing `StepResult.target.metadata` (`wait_used`, `wait_mode`, `wait_outcome`, `wait_adapter`, optional `wait_duration_ms`) only when `wait_for` is configured. JSON/HTML reporting preserves and safely renders wait metadata while redacting unsafe wait diagnostics fields. Observability-only scope; no wait behavior/retry behavior/schema/public-API/dependency/version changes.

- Phase 15F adapter-level explicit wait_for MVP: execute-path adapters now consume existing `ExecutionOptions.wait_for` + `timeout_ms` without schema/API changes. Playwright supports `visible`/`attached`/`enabled` pre-action waits; Appium supports `present`/`visible` pre-action waits with timeout-bounded visibility polling. Defaults remain backward-compatible when `wait_for` is `None`; retry cap/classification/metadata behavior unchanged. Added focused mock-based unit tests for wait modes, unsupported-mode failure clarity, and retry-with-wait behavior.
- Phase 15D retry observability metadata/reporting MVP: adapter execute paths now surface safe retry metadata on existing `StepResult.target.metadata` fields (`retry_attempts`, `retry_transient`, `retry_reason`, `retry_adapter`) for Playwright/Appium execution outcomes. JSON/HTML reporting preserves and safely renders retry metadata while redacting unsafe retry diagnostics fields. Observability-only scope; no retry behavior change, no schema/public-API/dependency/version changes.
- Phase 15B adapter-level transient retry/wait MVP: added conservative execute-only transient retry helpers in Playwright and Appium adapters (retry budget capped to 1, transient-message classification only, no resolver/grounding/provider retries). Added focused unit tests for transient/pass, permanent/fail, and retry-budget behavior. No public API/schema/dependency/version changes.
- Phase 14E docs/examples polish pass: added explicit run commands for key local examples, clarified direct-NL adoption wording around config/cost/provider/privacy-gated fallback behavior, and documented reserved pytest plugin flags (`--bubblegum-ai`, `--bubblegum-memory`). Docs/examples-only scope with no runtime/API/dependency/version changes.
- Phase 14C adoption/examples smoke-kit docs MVP added: `docs/adoption.md`, `docs/pytest-plugin.md`, `docs/ci.md`, plus new examples `examples/web_nl_quickstart.py`, `examples/ocr_callable_hydration_example.py`, and `examples/report_artifacts_example.py`. Updated `README.md`, `examples/README.md`, and `RELEASE_CHECKLIST.md` with adoption links and verification commands. Docs/examples-only scope with no runtime/API/dependency/version changes.

- Phase 19D UI Element Graph MVP added internal `ElementGraph` over `NormalizedElement` (`bubblegum/core/elements/graph.py`) with deterministic parent/child/sibling/nearby/label_for/same_row/same_container relationships and safe query helpers (`get_element`, `children_of`, `parent_of`, `siblings_of`, `nearby`, `labels_for`, `controls_for_label`, `elements_with_text`, `elements_by_role`) plus JSON-safe summary export. Added unit coverage for graph construction, deterministic relations, lookup helpers, unknown-id safety, and serialization safety. No resolver/ranker/adapter runtime integration, no SDK public API changes, no dependency/version changes.

## v0.0.5-alpha
- Release scope finalized for GitHub pre-release `v0.0.5-alpha` with package version `0.0.5a0` (PEP 440).
- Scope includes:
  - Phase 17A roadmap reset and `v0.0.5-alpha` planning
  - Phase 17B real smoke kit/adoption readiness audit
  - Phase 17C real smoke kit docs/examples MVP
  - Phase 17D smoke runner audit
  - Phase 17E dependency-free infra-free smoke runner MVP
  - Phase 17F smoke runner post-merge verification
  - Phase 17G release checklist collect-only baseline sync to 615
  - Phase 18B release metadata/docs/checklist preparation
- No runtime behavior changes.
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/network/browser/device CI smoke added.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.4-alpha
- Release scope finalized for GitHub pre-release `v0.0.4-alpha` with package version `0.0.4a0` (PEP 440).
- Scope includes:
  - Phase 14 adoption docs/examples polish
  - Phase 15B adapter-level transient retry MVP
  - Phase 15D retry observability metadata/reporting
  - Phase 15F adapter-level explicit `wait_for` MVP
  - Phase 15H wait observability metadata/reporting
- No SDK public API changes.
- No schema changes.
- No dependency changes.
- No provider/LLM/OCR/vision retry behavior changes.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

## v0.0.3-alpha
- Release scope finalized for GitHub pre-release `v0.0.3-alpha` with package version `0.0.3a0` (PEP 440).
- Phase 13 feature track included: VisualRefHydrator safe boundary/fail-safe behavior, deterministic web hydration (OCR/vision metadata), deterministic mobile hydration (`hierarchy_xml` text/content-desc/resource-id), sanitized SDK hydration diagnostics, JSON/HTML hydration diagnostics reporting, and hydration analytics summary.
- Publish-check hygiene from Phase 13C/13E retained for clean artifact verification (`rm -rf dist build *.egg-info` before `python -m build`).
- No runtime behavior changes, no public API breaking changes, no dependency changes in this release-prep slice.
- PyPI/TestPyPI publishing remains deferred; release target remains GitHub pre-release only.

- Phase 13Q hydration diagnostics analytics summary MVP: reporting analytics now include `hydration_summary` aggregate categorical counts (`total_events`, status/source/strategy/channel/reason) derived from report-safe hydration metadata only. Excludes refs and raw/sensitive payload-bearing fields. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13O hydration diagnostics reporting MVP: JSON reporting preserves sanitized hydration metadata with report-layer non-leakage guardrails; HTML reporting now renders a compact per-step hydration diagnostics section only when hydration metadata exists. Reporting-only scope with no SDK/public-API/runtime/adapter/resolver/provider/dependency/version changes.
- Phase 13M hydration diagnostics visibility MVP: SDK hydration boundary for visual refs now surfaces stable non-sensitive hydration metadata (status/reason/original_ref/hydrated_ref/channel/source/strategy plus match_field and match_count for ambiguous/no-match cases) on StepResult-facing outputs without changing hydration decisions or execution behavior. Sanitization excludes hierarchy XML, screenshots/bytes, base64/raw payloads, secrets, and candidate dumps. No public API/adapter/resolver/provider/dependency/version changes.
- Phase 13K deterministic mobile visual-ref hydration MVP: `VisualRefHydrator` now supports mobile hierarchy XML exact mapping for synthetic visual refs using deterministic metadata and priority fields `text` -> `content-desc` -> `resource-id`, emitting Appium-executable JSON XPath refs on unique matches. Stable fail-safe reasons are used for missing/invalid hierarchy, unsupported metadata, no-match, and ambiguous matches. No bbox/center-tap fallback, no screenshot/provider calls, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13I deterministic web visual-ref hydration MVP: `VisualRefHydrator` now maps supported synthetic refs to executable web refs using deterministic metadata only (OCR `matched_text`/`text` -> `text="..."`; vision `role` + label/text -> `role=...[name="..."]`, fallback text ref). Mobile visual hydration remains deferred fail-safe. No bbox/center-click fallback, no provider/screenshot calls added, and no public API/adapter/resolver/provider/dependency/version changes.
- Phase 13G visual ref hydration fail-safe MVP: added `VisualRefHydrator` abstraction and synthetic visual ref detection (`ocr://`, `vision://`) at SDK orchestration boundary for `act()` and `extract()`. Synthetic visual refs are never executed directly; hydration currently fails safe with stable `VisualRefHydrationError` when deterministic mapping is unavailable. No adapter/resolver/provider/public-API/dependency/version changes.
- Phase 13E publish-check artifact hygiene update: publish-readiness workflow now removes stale `dist/`, `build/`, and `*.egg-info` artifacts before `python -m build`; release checklist mirrors the same cleanup command to avoid ambiguous mixed-version artifact checks. No runtime/API/dependency/version changes.
- Phase 13C publish-readiness preparation: added manual-only `.github/workflows/publish-check.yml` to run packaging/validation/build/twine/benchmark/targeted-test/collection gates and upload `dist/` artifacts without publishing. Updated release checklist/readiness notes for deferred TestPyPI/PyPI posture and future trusted-publishing recommendation. No runtime/API/adapter/resolver/dependency/version changes.
- Phase 12D v0.0.2-alpha release-notes/checklist cleanup: finalized release wording and checklist gates for GitHub pre-release readiness. Scope remains documentation-only with no runtime/API/adapter/resolver/dependency/version changes.
- v0.0.2-alpha release scope summary finalized: callable OCR backend + OCR privacy gating; vision abstraction (`VisionProvider`) + callable backend (`CallableVisionProvider`); optional/dependency-light `OpenAIVisionProvider`; provider registration lifecycle (`configure_vision_provider` / `clear_vision_provider`); SDK screenshot-to-vision wiring with explicit privacy gates; `max_cost_level="high"` gate for provider-based screenshot vision; sanitized OpenAI diagnostics; API-correct manual OpenAI example; no mandatory OCR/OpenAI dependencies.
- Release/distribution posture reaffirmed: package version remains `0.0.2a0` for GitHub pre-release `v0.0.2-alpha`; PyPI/TestPyPI publishing remains deferred.
- Phase 11Z SDK cost gating for screenshot-to-vision provider invocation: runtime provider calls now require `ExecutionOptions.max_cost_level="high"` in addition to existing vision/privacy/provider/screenshot gates. Low/medium cost levels fail-safe skip screenshot request (when needed only for provider vision) and skip provider invocation; manual `vision_candidates` remain preserved and unblocked. Added SDK wiring/registration unit coverage.
- Phase 11X OpenAI vision diagnostics hardening: `OpenAIVisionProvider` now exposes sanitized failure metadata (`last_diagnostic` and `get_last_diagnostic()`) with stable `provider`/`code`/`stage`/`recoverable`/`message`/`exception_type` fields while preserving fail-safe `[]` behavior. Diagnostics exclude raw screenshot bytes, base64 payloads, request payloads, API keys/secrets, and raw provider response bodies. Added mock-only diagnostics coverage.
- Phase 11V docs/examples adoption hardening: added manual optional real-provider usage example (`examples/openai_vision_provider_manual_example.py`) and linked guidance in README/examples/docs for user-installed OpenAI SDK + `OPENAI_API_KEY`, required vision/privacy gates, and `clear_vision_provider()` teardown. No runtime/API/adapter/resolver/dependency/version changes; network tests/benchmarks remain unchanged.
- Phase 11T OpenAI vision hardening: `OpenAIVisionProvider` now validates explicit `model` (non-empty) and `timeout` (positive), preserves injected-client behavior, propagates timeout during optional lazy SDK client creation, and expands deterministic/mock-only parsing support for `output_text`, plain-string JSON, and simple nested response text shapes. Fail-safe `[]` error handling and screenshot-byte non-persistence policy remain unchanged; no SDK public API/adapter/dependency/version changes.
- Phase 11R optional OpenAI vision backend added (`bubblegum/core/vision/backends/openai.py`) via `OpenAIVisionProvider` implementing the existing VisionProvider contract (`detect_targets(image_bytes, instruction, context=None)`). Supports injected client or optional SDK client creation, encodes image bytes as base64 transport payload, requests structured JSON candidates, normalizes outputs, and fails safe to empty candidates on provider/parse/network errors. Includes mock-only unit coverage; no mandatory OpenAI dependency, no SDK public API/adapter/resolver changes, and no raw screenshot-byte persistence.
- Phase 11P docs/examples adoption slice added: new end-to-end callable vision provider lifecycle example (`examples/vision_callable_provider_example.py`) plus README/docs linkage and recommended setup/teardown (`configure_vision_provider(...)` + `clear_vision_provider()` in `finally`) with required gates (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`). No runtime/API/adapter/dependency/version changes; real OpenAI/Anthropic/Ollama providers remain deferred.
- Phase 11N public vision provider lifecycle API added: exported `configure_vision_provider(provider)` and `clear_vision_provider()` with provider contract validation (`detect_targets(...)`) and idempotent reset semantics. Registration does not invoke provider or bypass privacy/config gates; manual `vision_candidates` precedence, provider fail-safe behavior, and screenshot-byte non-persistence policy remain unchanged.
- Phase 11L callable vision enablement documentation added (`docs/phase-11l-callable-vision-enablements.md`), including callable contract/output examples, required privacy/config gates, manual `vision_candidates` vs optional SDK screenshot wiring guidance, provider non-invocation troubleshooting, raw screenshot persistence prohibition, synthetic `vision://` limitation, and explicit note that real OpenAI/Anthropic/Ollama vision providers remain deferred. Added provider lifecycle/API audit note and Phase 11M recommendation (keep private hook private for now; evaluate safe public registration lifecycle before real provider integrations).
- Phase 11J optional SDK screenshot-to-vision context wiring added: internal runtime plumbing can request screenshots and inject normalized `vision_candidates` only when all gates pass (`enable_vision`, `send_screenshots`, `process_screenshots_for_vision`, provider configured, screenshot present). Default behavior remains off; manually injected candidates are preserved; no raw screenshot bytes are stored in traces/metadata; no resolver/adapter/public API signature changes.
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
