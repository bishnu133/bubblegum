# Shared Test Fixtures

This directory is reserved for shared static fixtures used by tests across:
- `tests/unit/`
- `tests/integration/`
- `tests/e2e/`

Suggested fixture types:
- accessibility snapshots
- sample HTML pages
- sample Android hierarchy XML
- small JSON inputs/expected outputs

Phase 3A note:
- This directory is intentionally minimal and non-invasive.
- Existing benchmark fixtures remain under `tests/benchmarks/fixtures/`.
