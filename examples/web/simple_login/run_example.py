"""Phase 22C direct Bubblegum validation example (no Behave runtime).

This script intentionally executes a single login validation flow by calling
Bubblegum SDK functions directly, while `test_login.feature` remains
human-readable documentation only.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin

from bubblegum import act, configure_runtime, verify

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with one of:
  pip install -e ".[web]"
  pip install "bubblegum-ai[web]"
Then install browser binaries:
  python -m playwright install chromium
"""


async def run() -> None:
    from playwright.async_api import async_playwright

    config = configure_runtime(config_path="examples/web/simple_login/bubblegum.yaml")
    base_url = str(config.base_url or "")
    if not base_url:
        raise RuntimeError("`base_url` is required in examples/web/simple_login/bubblegum.yaml")

    login_url = urljoin(base_url.rstrip("/") + "/", "login")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=bool(config.headless))
        page = await browser.new_page()

        await page.goto(login_url)

        step_open = await verify(
            "Open /login and confirm page is ready",
            page=page,
            channel="web",
            selector="body",
            assertion_type="visible",
        )
        print("open:", step_open.status)

        step_user = await act(
            'Type "tomsmith" into Username',
            page=page,
            channel="web",
            selector='input[name="username"]',
            value="tomsmith",
        )
        print("username:", step_user.status)

        step_pass = await act(
            'Type "SuperSecretPassword!" into Password',
            page=page,
            channel="web",
            selector='input[name="password"]',
            value="SuperSecretPassword!",
        )
        print("password:", step_pass.status)

        step_click = await act(
            "Click Login",
            page=page,
            channel="web",
            selector='button[type="submit"]',
        )
        print("click:", step_click.status)

        step_verify = await verify(
            'Verify success text: "You logged into a secure area!"',
            page=page,
            channel="web",
            selector='text="You logged into a secure area!"',
            assertion_type="text_visible",
            expected_value="You logged into a secure area!",
        )
        print("verify_text:", step_verify.status)

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except ModuleNotFoundError:
        print(PLAYWRIGHT_INSTALL_HINT)
