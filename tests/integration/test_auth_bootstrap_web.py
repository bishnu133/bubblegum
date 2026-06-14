"""Real-browser auth/bootstrap check (W1).

Acceptance: a bootstrap callable establishes authenticated state (here, an init
script that injects the auth token before the page's own scripts run) and the
session lands on the authenticated page with ZERO UI login steps.

Gated by ``--playwright``. Runs on the session loop (like the shared-browser
fixtures) and builds its own session so it can pass ``bootstrap=``.

Run locally:
    pip install -e ".[web]" && python -m playwright install chromium
    python -m pytest tests/integration/test_auth_bootstrap_web.py -v --playwright
"""

from __future__ import annotations

import pytest

from bubblegum.session import BubblegumSession

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]


# Renders the authenticated view only when an auth token was injected before the
# page scripts ran; otherwise it shows a Sign in button (the UI login we skip).
_TOKEN_GATED_APP = """
<!doctype html><html lang="en"><head><title>App</title></head>
<body>
  <div id="root"></div>
  <script>
    if (window.__authToken) {
      document.getElementById('root').innerHTML = '<h1>Welcome back, tester</h1>';
    } else {
      document.getElementById('root').innerHTML =
        '<h1>Please log in</h1><button type="button">Sign in</button>';
    }
  </script>
</body></html>
"""


async def test_bootstrap_lands_on_authed_page_without_ui_login(bubblegum_browser):
    context = await bubblegum_browser.new_context()
    try:
        page = await context.new_page()

        async def login_via_api(p):
            # Stand-in for "call the login API and transplant the token". The
            # init script runs before the app's scripts on the next navigation.
            await p.add_init_script("window.__authToken = 'tok-123';")

        async with BubblegumSession.web(page, bootstrap=login_via_api) as s:
            await page.set_content(_TOKEN_GATED_APP)

            # Bubblegum confirms we're on the authenticated page...
            result = await s.verify("Welcome back, tester")
            assert result.status == "passed", result.error.message if result.error else result.status

            # ...with zero UI login: the Sign in affordance never rendered.
            assert await page.get_by_role("button", name="Sign in").count() == 0
            s.assert_all_passed()
    finally:
        await context.close()


async def test_without_bootstrap_the_app_shows_login(bubblegum_browser):
    """Control: same app, no bootstrap → the UI login is what you'd have to do."""
    context = await bubblegum_browser.new_context()
    try:
        page = await context.new_page()
        async with BubblegumSession.web(page) as s:  # no bootstrap
            await page.set_content(_TOKEN_GATED_APP)
            assert await page.get_by_role("button", name="Sign in").count() == 1
            result = await s.verify("Please log in")
            assert result.status == "passed"
    finally:
        await context.close()
