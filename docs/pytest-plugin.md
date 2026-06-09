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
- `--bubblegum-headed` — launch the `bubblegum_web` fixture browser in headed mode (default: headless).

These flags are currently optional and are not required for report generation flows above.

## Web fixtures (Phase 22E-2)

`bubblegum.pytest_plugin` ships two fixtures that remove session/page setup
boilerplate from web tests:

| Fixture | Scope | Yields | Requires |
|---|---|---|---|
| `bubblegum_web` | function | `BubblegumSession` wrapping a fresh Chromium page | `pytest-asyncio`, `playwright` |
| `widget_lab` | session | base URL string for the local widget-lab pages server | — |

The `bubblegum` marker labels tests that use these fixtures so they can
be filtered with `-m bubblegum` (e.g. to run only the high-level
NL flow tests).

```python
import pytest

pytestmark = [pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_select_india(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/select.html")

    await bubblegum_web.act("Select India from Country")

    assert await bubblegum_web.page.locator("#country").input_value() == "IN"
    bubblegum_web.assert_all_passed()
```

`bubblegum_web.page` (and `.driver`, `.channel`) expose the underlying
runtime handle so tests can navigate / assert against the page without
reaching into the session's privates.

### Headed mode for debugging

```bash
pytest tests/ -m bubblegum --bubblegum-headed
```

## State probes (Phase 22E-3)

`BubblegumSession` exposes async probes that resolve the NL target via
the same grounding chain as `act` / `verify` and then read state
directly from the Playwright locator.

| Probe | Returns | Backing call |
|---|---|---|
| `await s.is_checked(target)` | `bool` | `locator.is_checked()` |
| `await s.selected_value(target)` | `str` | `locator.input_value()` |
| `await s.is_visible(target)` | `bool` | `locator.is_visible()` |

```python
async def test_checkbox_flow(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/checkboxes.html")

    assert await bubblegum_web.is_checked("Marketing emails") is True
    assert await bubblegum_web.is_checked("Newsletter") is False

    await bubblegum_web.act("Check Newsletter")
    assert await bubblegum_web.is_checked("Newsletter") is True
```

Probes raise `BubblegumProbeError` when the target cannot be resolved.
They are web-only in 22E-3; mobile probes are tracked separately.

## Auto-screenshot on failure (Phase 22E-3)

When a `bubblegum_web` test fails, the fixture finalizer writes a
PNG to `<artifacts>/<sanitized-nodeid>-final.png`. Step-level failures
inside `act` / `verify` / `extract` write an additional
`<sanitized-nodeid>-step<N>.png` at the moment the step fails.

```bash
pytest tests/ -m bubblegum --bubblegum-artifacts=artifacts
# → artifacts/tests_integration_test_login.py_test_signin-step3.png
# → artifacts/tests_integration_test_login.py_test_signin-final.png
```

The artifacts directory is created on demand. Passing tests write no
files. Use `session.failure_screenshots` from inside a test to inspect
the paths captured so far.
