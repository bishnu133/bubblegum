"""Real-browser stability-wait checks (W2).

Acceptance: a spinner-gated button that only appears after the page settles
resolves reliably *without* a hardcoded sleep, because Bubblegum waits for
quiescence before grounding. Skips cleanly without a browser.

Run locally:
    pip install -e ".[web]" && python -m playwright install chromium
    python -m pytest tests/integration/test_stability_wait_web.py -v --playwright
"""

from __future__ import annotations

import pytest

from bubblegum.session import BubblegumSession

pytestmark = pytest.mark.playwright


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


async def _new_page():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed")
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch()
    except Exception as exc:
        await pw.stop()
        pytest.skip(f"Chromium not available: {exc}")
    page = await browser.new_page()
    return pw, browser, page


@pytest.mark.asyncio
async def test_spinner_gated_button_resolves_without_sleep():
    pw, browser, page = await _new_page()
    try:
        await page.set_content(_SPINNER_GATED_PAGE)
        async with BubblegumSession.web(page) as s:
            # No await asyncio.sleep(...) — stability wait settles the page first.
            result = await s.act("Click Continue")
        assert result.status in ("passed", "recovered"), (
            result.error.message if result.error else result.status
        )
        assert result.target is not None
    finally:
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_stability_diagnostics_reported_for_settled_page():
    """A static page settles immediately; wait_until_stable reports 'stable'."""
    pw, browser, page = await _new_page()
    try:
        await page.set_content("<button type='button'>Save</button>")
        from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

        adapter = PlaywrightAdapter(page)
        diag = await adapter.wait_until_stable(quiet_ms=200, timeout_ms=3000)
        assert diag["outcome"] == "stable"
        assert diag["network_idle"] is True
        assert diag["spinner_gone"] is True
    finally:
        await browser.close()
        await pw.stop()
