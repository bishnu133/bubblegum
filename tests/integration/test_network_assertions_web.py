"""Real-browser network assertion check (W4).

Acceptance: a step asserts a specific API call/status occurred and fails clearly
when it doesn't. The page fires a real ``fetch`` on button click; Bubblegum
records responses from the first step and ``verify(assertion_type="network")``
confirms the call.

Gated by ``--playwright``. Runs on the session loop, loads via ``goto(data:)``.

Run locally:
    pip install -e ".[web]" && python -m playwright install chromium
    python -m pytest tests/integration/test_network_assertions_web.py -v --playwright
"""

from __future__ import annotations

import urllib.parse

import pytest

from bubblegum.session import BubblegumSession

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]

# Clicking the button issues a GET to a data: URL (a real, observable response).
_PAGE = """
<!doctype html><html lang="en"><head><title>Net</title></head>
<body>
  <button type="button" id="go" onclick="fetch('https://example.com/api/ping').catch(()=>{})">Ping</button>
</body></html>
"""


def _data_url(html: str) -> str:
    return "data:text/html," + urllib.parse.quote(html)


async def test_network_assertion_passes_for_observed_call(bubblegum_browser):
    context = await bubblegum_browser.new_context()
    # Fulfil the request locally so the test needs no outbound network.
    await context.route(
        "https://example.com/api/ping",
        lambda route: route.fulfill(status=200, body="ok"),
    )
    try:
        page = await context.new_page()
        async with BubblegumSession.web(page) as s:
            await page.goto(_data_url(_PAGE))
            await s.act("Click Ping")  # fires the fetch; recorder captures it
            result = await s.verify(
                "ping call succeeded",
                assertion_type="network",
                expected_value="GET /api/ping 200",
            )
            assert result.status == "passed", result.error.message if result.error else result.status
    finally:
        await context.close()


async def test_network_assertion_fails_when_call_absent(bubblegum_browser):
    context = await bubblegum_browser.new_context()
    try:
        page = await context.new_page()
        async with BubblegumSession.web(page) as s:
            await page.goto(_data_url(_PAGE))
            # Never click — the call never happens, so the assertion must fail.
            result = await s.verify(
                "ping call succeeded",
                assertion_type="network",
                expected_value="GET /api/ping 200",
                timeout_ms=500,
            )
            assert result.status == "failed"
            assert result.error.error_type == "NetworkAssertionError"
    finally:
        await context.close()
