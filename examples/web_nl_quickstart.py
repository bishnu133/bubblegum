"""Web natural-language quickstart (local Playwright-only).

This example is import-safe and uses local HTML via ``page.set_content(...)``.
No external app, provider, OCR, or network setup is required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from bubblegum import act, extract, verify
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report


async def run() -> None:
    from playwright.async_api import async_playwright

    results = []
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.set_content(
            """
            <main>
              <h1>Checkout</h1>
              <button id='buy-btn'>Buy now</button>
              <p id='status'>idle</p>
              <script>
                document.getElementById('buy-btn').onclick = () => {
                  document.getElementById('status').textContent = 'order placed';
                }
              </script>
            </main>
            """
        )

        step1 = await act("Click the Buy now button", page=page)
        results.append(step1)

        step2 = await verify("Status shows order placed", page=page, selector="text=order placed")
        results.append(step2)

        step3 = await extract("Read the page heading text", page=page, selector="h1")
        results.append(step3)

        await browser.close()

    json_path = write_json_report(results, artifacts_dir / "web-nl-quickstart.json", title="Web NL Quickstart")
    html_path = write_html_report(results, artifacts_dir / "web-nl-quickstart.html", title="Web NL Quickstart")

    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote HTML report: {html_path}")


if __name__ == "__main__":
    asyncio.run(run())
