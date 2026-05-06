# Test Suite Structure

This repository organizes tests into the following directories:

- `tests/unit/`
  - Fast, isolated tests for core logic and contracts.
  - Examples: schemas, config wiring/loading, parser/inference logic, planner/options behavior, ranking/confidence logic, memory cache behavior, and error handling taxonomy.

- `tests/integration/`
  - Tests that validate interactions across components/adapters/resolvers.
  - May include optional dependency integrations (for example Playwright/Appium/LLM), which are gated by markers/flags.

- `tests/e2e/`
  - End-to-end flow tests spanning larger behavior slices.
  - Intended for deterministic workflows and higher-level system behavior checks.

- `tests/benchmarks/`
  - Benchmark fixtures and golden datasets used to evaluate grounding quality and regression trends.
  - Not part of default runtime behavior.

- `tests/fixtures/`
  - Shared static test artifacts (HTML/XML/JSON/etc.) for reuse across unit/integration/e2e tests.

## Markers vs Bubblegum plugin flags

- **Pytest markers/selectors** (`-m ...`) choose which tests run.
  - Examples: `-m playwright`, `-m appium`, `-m llm`, `-m memory`, `-m e2e`.
- **Bubblegum plugin flags** (`--bubblegum-...`) control Bubblegum runtime behavior and reporting.
  - Examples: `--bubblegum-config`, `--bubblegum-report`, `--bubblegum-report-json`, `--bubblegum-artifacts`, `--bubblegum-benchmark`.

Registered markers:

- `llm` — tests that call a real LLM provider.
- `memory` — tests that use disk-backed memory fixtures/SQLite.
- `appium` — tests requiring Appium server/device setup.
- `playwright` — tests requiring Playwright/browser setup.
- `e2e` — end-to-end tests that are optional in default local runs.

Default behavior keeps optional groups **off** unless explicitly selected.

## Running tests

Default-safe run:

```bash
pytest
```

This default run should not require:
- OpenAI API key
- Anthropic API key
- Appium server/device
- real browser runtime

Optional marked runs (selection via `-m`):

```bash
pytest -m llm -v
pytest -m memory -v
pytest -m appium -v
pytest -m playwright -v
pytest -m e2e -v
```

Bubblegum plugin reporting examples:

```bash
# HTML report
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report artifacts/bubblegum-report.html

# JSON report
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report-json artifacts/bubblegum-report.json

# HTML + JSON + artifacts directory
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-artifacts artifacts \
  --bubblegum-report artifacts/bubblegum-report.html \
  --bubblegum-report-json artifacts/bubblegum-report.json

# Benchmark validation
pytest --bubblegum-benchmark
```

Default-safe scaffolds:
- `tests/integration/test_phase3c_integration_scaffold.py` uses deterministic fake objects only.
- `tests/e2e/test_phase3c_e2e_scaffold.py` uses deterministic fake SDK flow only.

Note: `tests/integration/test_playwright_adapter.py` is marked `playwright` and is skipped unless selected with `-m playwright`.


## Benchmark validation (Phase 9 MVP RC baseline)

The benchmark runner has two modes and both are expected to pass in the current MVP RC state:

- Static validation (`python scripts/run_benchmarks.py`)
  - checks fixture schema compliance, snapshot existence, and static expected winner/confidence ranges.
- Execute validation (`python scripts/run_benchmarks.py --execute`)
  - runs deterministic execution against executable expectations.

Current expected results:

- static: 12/12 passed
- execute: total 12, executed 12, skipped 0, passed 12, failed 0

Notes:

- `execute_*` fields are executable-mode expectations and may differ from static expectations by design.
- `execute_allow_review=true` is benchmark-only review-pass handling and does not alter SDK/engine runtime behavior.
- Deterministic execute mode excludes Tier 3 AI/OCR/Vision resolvers.
- Memory benchmark execution uses ephemeral DB setup/pre-seeding and avoids `.bubblegum/memory.db`.

Useful checks:

```bash
python scripts/run_benchmarks.py
python scripts/run_benchmarks.py --execute
pytest tests/unit/test_run_benchmarks_execution.py -q
pytest tests/unit/test_benchmark_fixture_schema.py -q
```
