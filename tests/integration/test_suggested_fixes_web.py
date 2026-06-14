"""Real-browser self-healing suggested-fix check (R3).

Acceptance: after a healed run the report surfaces a copy-pasteable suggested
selector/label change and a ranked brittleness list. Here the step says "Login"
but the page only has a "Sign In" button — the fuzzy/synonym tier heals it, the
step is marked ``recovered``, and the advisory carries the old→new fix.

Gated by ``--playwright``. Runs on the session loop, loads via ``goto(data:)``.

Run locally:
    pip install -e ".[web]" && python -m playwright install chromium
    python -m pytest tests/integration/test_suggested_fixes_web.py -v --playwright
"""

from __future__ import annotations

import urllib.parse

import pytest

from bubblegum.reporting.suggested_fixes import build_suggested_fixes
from bubblegum.session import BubblegumSession

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]

_PAGE = """
<!doctype html><html lang="en"><head><title>App</title></head>
<body><button type="button">Sign In</button></body></html>
"""


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html)


async def test_heal_emits_suggested_fix_and_brittleness(bubblegum_browser):
    context = await bubblegum_browser.new_context()
    try:
        page = await context.new_page()
        async with BubblegumSession.web(page) as s:
            await page.goto(_data_url(_PAGE))

            # "Login" is healed to the page's "Sign In" via the synonym tier.
            result = await s.act("Click Login")
            assert result.status == "recovered", (
                result.error.message if result.error else result.status
            )

            healing = result.target.metadata.get("healing")
            assert healing and healing.get("applied")
            assert "Sign In" in (healing.get("new_ref") or "")
            assert healing.get("suggested_fix")  # copy-pasteable change

            # The report aggregates the heal into a ranked brittleness list.
            payload = build_suggested_fixes(s.results())
            assert payload["total_healed_steps"] >= 1
            assert payload["brittleness"][0]["heals"] >= 1
            assert payload["fixes"][0]["new_ref"] == "Sign In"
    finally:
        await context.close()
