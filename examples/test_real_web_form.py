"""
Form interactions smoke test — runs against https://the-internet.herokuapp.com

Tests more complex NL patterns: dropdowns, text areas, dynamic loading.
Run AFTER test_real_web.py passes.

Note: Some elements on this site have no accessible names or labels — those cases
use explicit selector= to show Bubblegum's graceful selector fallback.

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
        # The dropdown <select> has id="dropdown" but no aria label — use explicit
        # selector to demonstrate graceful fallback when NL alone can't ground it.
        print("\n── Dropdown (explicit selector fallback) ─────────────────────")
        await page.goto("https://the-internet.herokuapp.com/dropdown")
        await page.wait_for_load_state("domcontentloaded")

        r = await act('Select "Option 1" from dropdown', page=page,
                      selector="#dropdown", input_value="Option 1")
        _print("Select Option 1 (explicit selector)", r)
        results.append(r)

        r = await act('Select "Option 2" from dropdown', page=page,
                      selector="#dropdown", input_value="Option 2")
        _print("Select Option 2 (explicit selector)", r)
        results.append(r)

        # ── Inputs ────────────────────────────────────────────────────────
        # The number input has no label — use explicit selector.
        print("\n── Inputs (explicit selector fallback) ───────────────────────")
        await page.goto("https://the-internet.herokuapp.com/inputs")
        await page.wait_for_load_state("domcontentloaded")

        r = await act('Enter "42" into number field', page=page,
                      selector="input[type='number']", input_value="42")
        _print("Type 42 into number input (explicit selector)", r)
        results.append(r)

        # ── Dynamic Loading ────────────────────────────────────────────────
        # The Start button and Hello World heading are fully accessible.
        print("\n── Dynamic Loading (NL only) ─────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/dynamic_loading/1")
        await page.wait_for_load_state("domcontentloaded")

        r = await act("Click Start", page=page)
        _print("Click Start", r)
        results.append(r)

        # Wait for the hidden element to appear after the loader finishes.
        await page.wait_for_selector("#finish", state="visible", timeout=10000)

        # "Hello World!" — note the trailing exclamation mark in the actual text.
        r = await verify("Hello World!", page=page)
        _print("Verify Hello World visible", r)
        results.append(r)

        # ── Hovers ────────────────────────────────────────────────────────
        print("\n── Hovers (NL only) ──────────────────────────────────────────")
        await page.goto("https://the-internet.herokuapp.com/hovers")
        await page.wait_for_load_state("domcontentloaded")

        r = await verify("Hovers is visible", page=page)
        _print("Verify Hovers heading", r)
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
