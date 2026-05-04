# Benchmark Fixtures (Phase 2 Scaffold)

This directory now contains a deterministic benchmark-fixture scaffold under `tests/benchmarks/fixtures`.

## Relationship to existing `golden_dataset`

- `tests/benchmarks/golden_dataset` is retained as-is for historical/legacy scenario composition.
- `tests/benchmarks/fixtures` is the new Phase 2 schema-driven scaffold for deterministic validation and reporting.
- This PR does **not** remove or mutate legacy datasets.

## Fixture files

- `fixtures/schema.json`: schema contract for benchmark fixtures.
- `fixtures/cases.json`: initial benchmark cases spanning required categories.
- `fixtures/snapshots/web/*.html`: sample DOM snapshots.
- `fixtures/snapshots/android/*.xml`: sample Appium hierarchy snapshots.

## Runner

Use:

```bash
python scripts/run_benchmarks.py
```

This Phase 2 runner is intentionally deterministic and does not execute real browser/Appium/AI calls.
