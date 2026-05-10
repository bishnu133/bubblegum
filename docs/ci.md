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
            --bubblegum-report-json artifacts/bubblegum-report.json

      - name: Upload Bubblegum artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: bubblegum-artifacts
          path: artifacts/
```

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
