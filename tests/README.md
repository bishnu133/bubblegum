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

## Markers and optional test groups

Registered markers:

- `llm` — tests that call a real LLM provider.
- `memory` — tests that use disk-backed memory fixtures/SQLite.
- `appium` — tests requiring Appium server/device setup.
- `playwright` — tests requiring Playwright/browser setup.
- `e2e` — end-to-end tests that are optional in default local runs.

Default behavior keeps optional groups **off** unless explicitly enabled.

## Running tests

Default test run:

```bash
pytest
```

This default run should not require:
- OpenAI API key
- Anthropic API key
- Appium server/device
- real browser runtime

Run optional groups:

```bash
# LLM integration
pytest -m llm --llm -v

# Disk-backed memory integration
pytest -m memory --memory -v

# Appium integration
pytest -m appium --appium -v

# Playwright integration
pytest -m playwright --playwright -v

# E2E tests
pytest -m e2e --e2e -v
```

You can combine markers/flags as needed for local or CI pipelines.


Default-safe scaffolds:
- `tests/integration/test_phase3c_integration_scaffold.py` uses deterministic fake objects only.
- `tests/e2e/test_phase3c_e2e_scaffold.py` uses deterministic fake SDK flow only.

Note: `tests/integration/test_playwright_adapter.py` is marked `playwright` and is skipped unless `--playwright` is passed.
