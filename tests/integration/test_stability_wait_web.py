"""Real-browser stability-wait checks (W2).

Acceptance: a spinner-gated button that only appears after the page settles
resolves reliably *without* a hardcoded sleep, because Bubblegum waits for
quiescence before grounding.

Gated by ``--playwright``. Uses the shared ``bubblegum_web`` fixture (not a
manual Playwright lifecycle) so these run on the same loop scope as the rest of
the browser suite.

Run locally:
    pip install -e ".[web]" && python -m playwright install chromium
    python -m pytest tests/integration/test_stability_wait_web.py -v --playwright
"""

from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


# A spinner is shown for ~1.2s; only then is the real "Continue" button added.
# The spinner matches the default stability_spinner_selectors ([role=progressbar]).
_SPINNER_GATED_PAGE = """
<!doctype html><html lang="en"><head><title>Loading demo</title></head>
<body>
  <div id="app">
    <div role="progressbar" class="spinner">Loading…</div>
  </div>
  <script>
    setTimeout(function () {
      var app = document.getElementById('app');
      app.innerHTML = '<button type="button" id="go">Continue</button>';
    }, 1200);
  </script>
</body></html>
"""


async def test_spinner_gated_button_resolves_without_sleep(bubblegum_web):
    # No await asyncio.sleep(...) — stability wait settles the page first.
    await bubblegum_web.page.set_content(_SPINNER_GATED_PAGE)
    result = await bubblegum_web.act("Click Continue")
    assert result.status in ("passed", "recovered"), (
        result.error.message if result.error else result.status
    )
    assert result.target is not None


async def test_stability_diagnostics_reported_for_settled_page(bubblegum_web):
    """A static page settles immediately; wait_until_stable reports 'stable'."""
    await bubblegum_web.page.set_content("<button type='button'>Save</button>")
    adapter = PlaywrightAdapter(bubblegum_web.page)
    diag = await adapter.wait_until_stable(quiet_ms=200, timeout_ms=3000)
    assert diag["outcome"] == "stable"
    assert diag["network_idle"] is True
    assert diag["spinner_gone"] is True
