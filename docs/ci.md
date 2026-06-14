# CI Usage (GitHub Actions)

This page provides an adoption-first CI snippet for validation, tests, and report artifacts.

## Suggested workflow snippet

```yaml
name: bubblegum-ci
on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[test]"

      - name: Validate package
        run: python scripts/validate_package.py

      - name: Run focused tests with reports
        run: |
          pytest \
            --bubblegum-config bubblegum.yaml \
            --bubblegum-artifacts artifacts \
            --bubblegum-report artifacts/bubblegum-report.html \
            --bubblegum-report-json artifacts/bubblegum-report.json \
            --bubblegum-report-junit artifacts/bubblegum-report.xml \
            --bubblegum-report-allure artifacts/allure-results

      - name: Upload Bubblegum artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bubblegum-artifacts
          path: artifacts/

      - name: Publish test results
        if: always()
        uses: EnricoMi/publish-unit-test-result-action@v2
        with:
          junit_files: artifacts/bubblegum-report.xml
```

`--bubblegum-report-junit` writes standard JUnit XML that Jenkins, GitLab CI,
Azure DevOps and CircleCI consume natively for their pass/fail test tabs and
history. `passed`/`recovered` steps map to passing test cases (a heal is
surfaced in `<system-out>` so it never fails the build), `failed` maps to
`<failure>`, and `skipped`/`dry_run` map to `<skipped>`.

`--bubblegum-report-allure` writes Allure 2 result files (resolver, confidence,
self-healing steps and screenshot attachments per step). Bubblegum produces
these with the standard library alone — no extra Python package is needed to
generate them. View them with the Allure command-line tool:

```bash
allure serve artifacts/allure-results
```

## Parallel runs (pytest-xdist)

Bubblegum's memory cache (`.bubblegum/memory.db`) is safe to share across
`pytest-xdist` workers. The SQLite connection is opened in **WAL journal mode**
with a **busy-timeout**, so multiple worker processes can read and write
concurrently without "database is locked" errors, and cache hits are shared
across workers (a resolution recorded by one worker is replayed by the others):

```bash
pytest -n auto \
    --bubblegum-config bubblegum.yaml \
    --bubblegum-report-junit artifacts/bubblegum-report.xml
```

Cache semantics under parallelism:

- **Shared DB (default):** all workers use the same `.bubblegum/memory.db`. WAL +
  busy-timeout serialize contended writes; reads never block writes. This keeps
  cross-worker cache hits, which is usually what you want.
- **Isolated per-worker caches (optional):** if you prefer no sharing, point each
  worker at `.bubblegum/memory.<worker>.db` (e.g. keyed on the
  `PYTEST_XDIST_WORKER` env var) and merge afterwards with the memory layer's
  `export()` / `import_from()`. WAL can be turned off (`MemoryLayer(wal=False)`)
  for filesystems that don't support it, such as some network mounts.

## Publishing posture note

- `.github/workflows/publish-check.yml` is a **manual, non-publishing readiness workflow**.
- TestPyPI/PyPI publication remains deferred in this track.
- Keep release/distribution focus on GitHub pre-release posture until a dedicated publishing phase.

## Real smoke kit usage with CI posture

Recommended operator flow:

1. Run infra-free smoke examples locally (fast signal).
2. Run Playwright example manually where browser setup is available.
3. Keep Appium/OpenAI provider smoke manual and non-CI-gated for this phase.

Infra-free commands:

```bash
python examples/ocr_callable_hydration_example.py
python examples/report_artifacts_example.py
```

Optional local helper (not a CI gate for browser/device/provider flows):

```bash
python scripts/smoke_examples.py --dry-run
python scripts/smoke_examples.py
```

Playwright local smoke commands:

```bash
python -m pip install -e ".[web]"
python -m playwright install chromium
python examples/web_nl_quickstart.py
```

Expected report artifact paths:
- `artifacts/report-artifacts-example.json`
- `artifacts/report-artifacts-example.html`
- `artifacts/web-nl-quickstart.json`
- `artifacts/web-nl-quickstart.html`

These report outputs are local JSON/HTML observability artifacts and can be uploaded using `actions/upload-artifact`.
