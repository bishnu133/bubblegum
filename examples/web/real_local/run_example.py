"""Acme Notes — Bubblegum's "first 60 seconds" sample app.

A three-page local web app (login → dashboard → settings) driven entirely
by natural-language steps. No selectors, no test IDs, no backend — the
pages are served from ./pages by the same static-server helper the pytest
fixtures use.

Run from the repo root:

    pip install -e ".[web,test]"
    python -m playwright install chromium
    python examples/web/real_local/run_example.py            # headless
    python examples/web/real_local/run_example.py --headed   # watch it

Demo credentials: tester / bubblegum!
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from bubblegum.session import BubblegumSession
from bubblegum.testing.widget_lab import start_widget_lab_server

PAGES_DIR = Path(__file__).resolve().parent / "pages"

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with:
  pip install -e ".[web]"
Then install browser binaries:
  python -m playwright install chromium
"""


async def run(headed: bool) -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(PLAYWRIGHT_INSTALL_HINT, file=sys.stderr)
        return 2

    server, base_url = start_widget_lab_server(pages_dir=PAGES_DIR)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed)
            try:
                page = await browser.new_page()
                page.set_default_timeout(5_000)

                async with BubblegumSession.web(page) as s:
                    # --- Sign in ------------------------------------------
                    await s.goto(f"{base_url}/login.html")
                    await s.act('Enter "tester" into Username')
                    await s.act('Enter "bubblegum!" into Password')
                    await s.act("Click Sign in")
                    assert await s.is_visible("Dashboard"), "expected the dashboard after login"

                    # --- Change a setting ---------------------------------
                    await s.act("Click the Settings link")
                    await s.act("Check Email notifications")
                    await s.act("Select German from Language")
                    await s.act("Click Save")
                    assert await s.is_checked("Email notifications")
                    assert await s.is_visible("Settings saved.")

                    s.assert_all_passed()
                    summary = s.summary()

                print(
                    f"\n✅ Acme Notes flow complete: "
                    f"{summary['passed']}/{summary['total']} steps passed "
                    f"in {summary['duration_ms']}ms"
                )
                return 0
            finally:
                await browser.close()
    finally:
        server.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Acme Notes sample flow.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window.")
    args = parser.parse_args()
    return asyncio.run(run(headed=args.headed))


if __name__ == "__main__":
    raise SystemExit(main())
