"""Minimal Playwright + Bubblegum template.

Requirements:
  pip install bubblegum-ai playwright
  playwright install chromium
"""

from __future__ import annotations

import asyncio

from bubblegum import act, extract, recover, verify


async def main() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Template target page; replace with your application URL.
        await page.goto("https://example.com")

        # Recover a stale selector in an existing test.
        recovered = await recover(
            page=page,
            failed_selector="#login-btn",
            intent="Click Login",
            channel="web",
        )
        print("recover status:", recovered.status)

        # Natural-language action.
        acted = await act("Click More information", page=page, channel="web")
        print("act status:", acted.status)

        # Natural-language verification.
        checked = await verify(
            "Example Domain visible",
            page=page,
            channel="web",
            assertion_type="text_visible",
            expected_value="Example Domain",
        )
        print("verify status:", checked.status)

        # Natural-language extraction.
        extracted = await extract("Get heading text", page=page, channel="web")
        value = (extracted.target.metadata or {}).get("extracted_value") if extracted.target else None
        print("extract status:", extracted.status, "value:", value)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
