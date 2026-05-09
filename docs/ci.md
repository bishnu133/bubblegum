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
