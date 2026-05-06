"""Minimal Playwright + Bubblegum template.

Requirements:
  pip install -e ".[web]"
  python -m playwright install chromium
  # package users: pip install "bubblegum-ai[web]"
"""

from __future__ import annotations

import asyncio

from bubblegum import act, extract, recover, verify


PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install web dependencies with one of:
  pip install -e ".[web]"
  pip install "bubblegum-ai[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

PLAYWRIGHT_BROWSER_HINT = """Playwright browser launch failed.
Common fixes:
  1) Install browser binaries: python -m playwright install chromium
  2) Ensure Playwright is installed: pip install -e ".[web]"
     (or pip install "bubblegum-ai[web]")
  3) In restricted/proxy environments, verify package/binary download access.
"""

RECOVER_TEMPLATE_HINT = (
    "recover demo may need a real app/selector; this is expected for templates."
)


async def main() -> None:
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError:
        print(PLAYWRIGHT_INSTALL_HINT)
        return

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Deterministic local smoke target; replace with your app URL/content later.
            await page.set_content("""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Bubblegum Playwright Quickstart</title>
  </head>
  <body>
    <main>
      <h1>Example Domain</h1>
      <p>This is deterministic local quickstart content.</p>
      <a href="#more-info">More information</a>
      <section id="more-info">
        <p>Smoke target ready for act verify extract.</p>
      </section>
    </main>
  </body>
</html>
""")

            # Optional recover demo: expected to require a real app + stale selector.
            try:
                recovered = await recover(
                    page=page,
                    failed_selector="#login-btn",
                    intent="Click Login",
                    channel="web",
                )
                print("recover status:", recovered.status)
                if recovered.status == "failed":
                    print(RECOVER_TEMPLATE_HINT)
            except Exception as exc:
                print("recover status: failed", f"({exc})")
                print(RECOVER_TEMPLATE_HINT)

            # Deterministic smoke action using an explicit selector.
            acted = await act(
                "Click More information",
                page=page,
                channel="web",
                selector='text="More information"',
            )
            print("act status:", acted.status)

            # Deterministic smoke verification with explicit selector + expected text.
            checked = await verify(
                "Confirm heading text is visible",
                page=page,
                channel="web",
                selector='text="Example Domain"',
                assertion_type="text_visible",
                expected_value="Example Domain",
            )
            print("verify status:", checked.status)

            # Deterministic smoke extraction via explicit heading selector.
            extracted = await extract(
                "Get text of Example Domain heading",
                page=page,
                channel="web",
                selector="h1",
            )
            value = (extracted.target.metadata or {}).get("extracted_value") if extracted.target else None
            print("extract status:", extracted.status, "value:", value)

            await browser.close()
    except Exception as exc:
        print(f"Playwright quickstart failed: {exc}")
        print(PLAYWRIGHT_BROWSER_HINT)


if __name__ == "__main__":
    asyncio.run(main())
