"""API-based auth bootstrap example (W1).

The single biggest speed + flakiness win is to NOT log in through the UI on
every test. Pass an async ``bootstrap`` callable to ``BubblegumSession.web`` —
it runs once on session entry, receives the Playwright ``page``, and establishes
authenticated state via API (cookies / localStorage / token). Your test then
starts already authenticated, with zero UI login steps.

This example is provider-agnostic: replace ``get_token_via_api`` with your real
login call. Run it against any app you can authenticate by cookie/token.

Install:
  pip install -e ".[web]" && python -m playwright install chromium
Run:
  python examples/web/auth_bootstrap/run_example.py --url https://your-app.test
"""

from __future__ import annotations

import argparse
import asyncio

from bubblegum.session import BubblegumSession


async def get_token_via_api(username: str, password: str) -> str:
    """Stand-in for your real login API call.

    In a real test you'd POST to your auth endpoint (httpx/requests/aiohttp) and
    return the session token/JWT, e.g.:

        async with httpx.AsyncClient() as c:
            r = await c.post("https://your-app.test/api/login",
                             json={"username": username, "password": password})
            return r.json()["token"]
    """
    return "demo-token-123"


def make_bootstrap(base_url: str):
    """Build a bootstrap that transplants an API-obtained session into the page."""

    async def bootstrap(page):
        token = await get_token_via_api("tester", "bubblegum!")

        # Pick whichever your app uses to recognise a session:
        # 1) Cookie-based session:
        await page.context.add_cookies(
            [{"name": "session", "value": token, "url": base_url}]
        )
        # 2) Token in localStorage (set before app scripts run on next navigation):
        await page.add_init_script(f"window.localStorage.setItem('token', {token!r});")
        # 3) Or an Authorization header for every request:
        # await page.set_extra_http_headers({"Authorization": f"Bearer {token}"})

    return bootstrap


async def main(url: str, authed_path: str, expect_text: str) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print('Playwright not installed. pip install -e ".[web]" '
              "&& python -m playwright install chromium")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await (await browser.new_context()).new_page()

            # The whole point: no UI login steps — bootstrap establishes the
            # session, then we land directly on an authenticated page.
            async with BubblegumSession.web(page, bootstrap=make_bootstrap(url)) as s:
                await s.goto(url.rstrip("/") + authed_path)
                result = await s.verify(f"{expect_text} is visible")
                s.assert_all_passed()
                print(f"[{result.status}] landed on authed page — zero UI login steps")
                return 0 if result.status in ("passed", "recovered") else 1
        finally:
            await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bubblegum API auth-bootstrap example")
    ap.add_argument("--url", required=True, help="App base URL (e.g. https://your-app.test)")
    ap.add_argument("--authed-path", default="/dashboard", help="Path that requires auth")
    ap.add_argument("--expect-text", default="Dashboard", help="Text proving you're authed")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.url, args.authed_path, args.expect_text)))
