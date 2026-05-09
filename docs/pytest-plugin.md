# Pytest Plugin Usage

Bubblegum exposes `bubblegum.pytest_plugin` to generate report artifacts during test runs.

## Common CLI patterns

```bash
# HTML only
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report artifacts/bubblegum-report.html

# JSON only
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-report-json artifacts/bubblegum-report.json

# HTML + JSON + explicit artifacts folder
pytest --bubblegum-config bubblegum.yaml \
  --bubblegum-artifacts artifacts \
  --bubblegum-report artifacts/bubblegum-report.html \
  --bubblegum-report-json artifacts/bubblegum-report.json

# Optional benchmark summary at session end
pytest --bubblegum-benchmark
```

## Minimal sample test pattern

```python
from bubblegum import act, verify

async def test_checkout_smoke(page):
    await page.set_content("<button id='buy'>Buy</button><h1>Done</h1>")
    step = await act("Click Buy", page=page, selector="#buy")
    assert step.status in {"passed", "recovered"}

    result = await verify("Done is visible", page=page, selector="text=Done")
    assert result.status in {"passed", "recovered"}
```

## Artifact expectations

- HTML report: readable test session summary + step traces.
- JSON report: structured output for analytics and downstream ingestion.
- Hydration diagnostics/analytics fields are sanitized for reporting.


## Additional available/reserved flags

- `--bubblegum-ai` — available/reserved for future AI-related pytest behavior toggles.
- `--bubblegum-memory` — available/reserved for future memory-related pytest behavior toggles.

These flags are currently optional and are not required for report generation flows above.
