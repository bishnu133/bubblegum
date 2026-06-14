"""Real-browser a11y assertion checks (V2).

These exercise the *vendored* axe-core build running inside a real Chromium via
the Playwright adapter — the part the fake-page unit tests cannot cover.

Gated by ``--playwright``. Uses the shared ``bubblegum_web`` fixture (not a
manual Playwright lifecycle) so these run on the same loop scope as the rest of
the browser suite.

Run locally with:
    pip install -e ".[a11y]" && python -m playwright install chromium
    python -m pytest tests/integration/test_a11y_web.py -v --playwright
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


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


async def test_a11y_detects_known_violation(bubblegum_web):
    await bubblegum_web.page.set_content(_PAGE_WITH_VIOLATION)
    result = await bubblegum_web.verify("page has no critical a11y violations", assertion_type="a11y")

    assert result.status == "failed"
    ids = {v["id"] for v in result.target.metadata["a11y_violations"]}
    assert "image-alt" in ids
    # The failure message is a readable, per-rule list.
    assert "image-alt" in (result.error.message or "")


async def test_a11y_passes_on_clean_page(bubblegum_web):
    await bubblegum_web.page.set_content(_CLEAN_PAGE)
    result = await bubblegum_web.verify("page has no critical a11y violations", assertion_type="a11y")
    assert result.status == "passed", result.error.message if result.error else ""
    assert result.target.metadata["a11y_violation_count"] == 0
