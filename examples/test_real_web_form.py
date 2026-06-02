"""
Form interactions smoke test — runs against https://the-internet.herokuapp.com

Tests more complex NL patterns: dropdowns, text areas, file inputs.
Run AFTER test_real_web.py passes.

Usage
-----
  python examples/test_real_web_form.py
  python examples/test_real_web_form.py --headed
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).parent.parent
sys.path.insert(0, str(_HERE))

from bubblegum import act, extract, verify
from bubblegum.core.config import BubblegumConfig
from bubblegum.core import sdk
from bubblegum.reporting.html_report import write_html_report


def _print(label, r):
    icon = "✓" if r.status in ("passed", "recovered") else "✗"
    ref = r.target.ref if r.target else "—"
    err = f" ERROR: {r.error.message}" if r.error else ""
    print(f"  {icon} {label} → {r.status} ({r.target.resolver_name if r.target else '—'}) ref={ref!r}{err}")


async def run(headed: bool) -> int:
    cfg = BubblegumConfig.load()
    cfg.ai.enabled = False
    sdk.configure_runtime(config=cfg)

    from playwright.async_api import async_playwright

    results = []
    failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        page = await browser.new_page()

        # ── Dropdown ──────────────────────────────────────────────────────
        print("\n── Dropdown ──────────────────────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/dropdown")
        await page.wait_for_load_state("domcontentloaded")

        r = await act("Select Option 1 from Dropdown", page=page)
        _print("Select Option 1", r)
        results.append(r)

        r = await act("Select Option 2 from Dropdown", page=page)
        _print("Select Option 2", r)
        results.append(r)

        # ── Inputs ────────────────────────────────────────────────────────
        print("\n── Inputs ────────────────────────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/inputs")
        await page.wait_for_load_state("domcontentloaded")

        r = await act('Enter "42" into the number input', page=page)
        _print('Type 42 into number input', r)
        results.append(r)

        # ── Key Presses ───────────────────────────────────────────────────
        print("\n── Key Presses ───────────────────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/key_presses")
        await page.wait_for_load_state("domcontentloaded")

        r = await verify("Target field visible", page=page)
        _print("Verify target field visible", r)
        results.append(r)

        # ── Dynamic Loading ────────────────────────────────────────────────
        print("\n── Dynamic Loading ───────────────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/dynamic_loading/1")
        await page.wait_for_load_state("domcontentloaded")

        r = await act("Click Start", page=page)
        _print("Click Start", r)
        results.append(r)

        # Wait for element to appear
        await page.wait_for_selector("#finish", state="visible", timeout=10000)

        r = await verify("Hello World is visible", page=page)
        _print("Verify Hello World", r)
        results.append(r)

        await browser.close()

    for r in results:
        if r.status == "failed":
            failed += 1

    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    html_path = write_html_report(results, artifacts / "form-test.html", title="Form Tests")

    print(f"\n── Summary ──  Total: {len(results)}  Passed: {len(results)-failed}  Failed: {failed}")
    print(f"  Report: open {html_path}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--headed", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args.headed)))
