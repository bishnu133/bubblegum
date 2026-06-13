"""Real-browser a11y assertion checks (V2).

These exercise the *vendored* axe-core build running inside a real Chromium via
the Playwright adapter — the part the fake-page unit tests cannot cover. They
skip cleanly when Playwright or its browser binary is unavailable, so the suite
stays green in environments without a browser.

Run locally with:
    pip install -e ".[a11y]" && python -m playwright install chromium
    python -m pytest tests/integration/test_a11y_web.py -v
"""

from __future__ import annotations

import pytest

from bubblegum.session import BubblegumSession

pytestmark = pytest.mark.playwright


async def _new_page():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.skip("Playwright not installed; install with pip install -e \".[a11y]\"")
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch()
    except Exception as exc:  # browser binary missing
        await pw.stop()
        pytest.skip(f"Chromium not available: {exc}")
    page = await browser.new_page()
    return pw, browser, page


_PAGE_WITH_VIOLATION = """
<!doctype html><html lang="en"><head><title>Bad</title></head>
<body>
  <img src="logo.png">           <!-- image-alt: critical violation -->
  <h1>Welcome</h1>
</body></html>
"""

_CLEAN_PAGE = """
<!doctype html><html lang="en"><head><title>Good</title></head>
<body>
  <img src="logo.png" alt="Company logo">
  <h1>Welcome</h1>
  <button type="button">Continue</button>
</body></html>
"""


@pytest.mark.asyncio
async def test_a11y_detects_known_violation():
    pw, browser, page = await _new_page()
    try:
        await page.set_content(_PAGE_WITH_VIOLATION)
        async with BubblegumSession.web(page) as s:
            result = await s.verify("page has no critical a11y violations", assertion_type="a11y")

        assert result.status == "failed"
        ids = {v["id"] for v in result.target.metadata["a11y_violations"]}
        assert "image-alt" in ids
        # The failure message is a readable, per-rule list.
        assert "image-alt" in (result.error.message or "")
    finally:
        await browser.close()
        await pw.stop()


@pytest.mark.asyncio
async def test_a11y_passes_on_clean_page():
    pw, browser, page = await _new_page()
    try:
        await page.set_content(_CLEAN_PAGE)
        async with BubblegumSession.web(page) as s:
            result = await s.verify("page has no critical a11y violations", assertion_type="a11y")
        assert result.status == "passed", result.error.message if result.error else ""
        assert result.target.metadata["a11y_violation_count"] == 0
    finally:
        await browser.close()
        await pw.stop()
