# Benchmark Fixtures (Phase 9 MVP RC Status)

This directory contains the deterministic benchmark fixture suite under `tests/benchmarks/fixtures`.

## Relationship to existing `golden_dataset`

- `tests/benchmarks/golden_dataset` is retained for historical/legacy scenario composition.
- `tests/benchmarks/fixtures` is the schema-driven deterministic benchmark contract used for validation and reporting.
- Current MVP RC status does not remove or mutate legacy datasets.

## Fixture files

- `fixtures/schema.json`: schema contract for benchmark fixtures.
- `fixtures/cases.json`: benchmark cases spanning required categories.
- `fixtures/snapshots/web/*.html`: sample DOM snapshots.
- `fixtures/snapshots/android/*.xml`: sample Appium hierarchy snapshots.

## Validation modes

The benchmark runner supports two complementary modes:

1. **Static validation** (`python scripts/run_benchmarks.py`)
   - Validates fixture schema compliance.
   - Validates referenced snapshots exist.
   - Validates static expected winner/confidence range assertions.

2. **Execute validation** (`python scripts/run_benchmarks.py --execute`)
   - Runs deterministic benchmark execution.
   - Produces executable-mode pass/fail results against `execute_*` expectations.

## Current benchmark status

Expected benchmark status for current MVP RC baseline:

- **static**: 12/12 passed
- **execute**: total 12, executed 12, skipped 0, passed 12, failed 0

## Static vs execute expectations

- Static expectations validate fixture-level intent and confidence contracts.
- `execute_*` fields are executable-mode expectations and may intentionally differ from static expectations.
- This split is intentional and documents fixture correctness separately from deterministic execution outcomes.

## Review-pass handling

- `execute_allow_review=true` is **benchmark-only** review-pass handling.
- It does **not** change SDK or grounding engine runtime behavior.
- Production/runtime decision semantics remain unchanged.

## Determinism and resolver scope

- Deterministic benchmark execution excludes Tier 3 AI/OCR/Vision resolvers.
- Memory benchmark behavior uses ephemeral DB setup/pre-seeding and avoids `.bubblegum/memory.db`.

## Commands

```bash
python scripts/run_benchmarks.py
python scripts/run_benchmarks.py --execute
pytest tests/unit/test_run_benchmarks_execution.py -q
pytest tests/unit/test_benchmark_fixture_schema.py -q
```
