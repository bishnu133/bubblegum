"""
Real-web smoke test — runs against https://the-internet.herokuapp.com

This is the recommended first script to run locally to validate that Bubblegum
works end-to-end on a real web page with no explicit selectors.

Prerequisites
-------------
  pip install bubblegum-ai[web]        # or: pip install -e ".[web]"
  playwright install chromium

Usage
-----
  python examples/test_real_web.py                     # deterministic only (free)
  python examples/test_real_web.py --llm               # enable LLM fallback
  python examples/test_real_web.py --headed             # see the browser window

What it tests
-------------
  1. Login form — type into Username and Password, click Login   (NL only, no selectors)
  2. Secure page verification — verify the flash message appears after login
  3. Text extraction  — extract the flash message text
  4. Logout           — click Logout link
  5. Fuzzy match      — "Sign in" resolves to "Login" button (synonym healing)

The test uses https://the-internet.herokuapp.com/login which accepts:
  username: tomsmith
  password: SuperSecretPassword!
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).parent.parent  # repo root
sys.path.insert(0, str(_HERE))

from bubblegum import act, extract, verify, BubblegumSession
from bubblegum.core.config import BubblegumConfig
from bubblegum.core import sdk
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_result(label: str, result) -> None:
    icon = "✓" if result.status == "passed" else "✗"
    conf = f"conf={result.confidence:.2f}" if result.confidence else ""
    resolver = result.target.resolver_name if result.target else "—"
    ref = result.target.ref if result.target else "—"
    err = f"  ERROR: {result.error.message}" if result.error else ""
    print(f"  {icon} [{result.status:8}] {label}")
    print(f"        resolver={resolver}  {conf}")
    print(f"        ref={ref!r}{err}")
    if result.target and result.target.metadata.get("extracted_value"):
        print(f"        value={result.target.metadata['extracted_value']!r}")
    print()


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

async def run_login_suite(page, results: list) -> None:
    print("\n── Login Form ─────────────────────────────────────────────────")
    await page.goto("https://the-internet.herokuapp.com/login")
    await page.wait_for_load_state("domcontentloaded")

    # Step 1 — type into Username (NL-only, value + target parsed from sentence)
    r = await act('Enter "tomsmith" into Username', page=page)
    _print_result('Enter "tomsmith" into Username', r)
    results.append(r)

    # Step 2 — type into Password
    r = await act('Enter "SuperSecretPassword!" into Password', page=page)
    _print_result('Enter "SuperSecretPassword!" into Password', r)
    results.append(r)

    # Step 3 — click Login (pure NL click)
    r = await act("Click Login", page=page)
    _print_result("Click Login", r)
    results.append(r)


async def run_secure_page_suite(page, results: list) -> None:
    print("── Secure Page ────────────────────────────────────────────────")

    # Step 4 — verify flash message exists
    r = await verify("You logged into a secure area", page=page)
    _print_result("Verify flash message visible", r)
    results.append(r)

    # Step 5 — extract flash message text; flash div has no ARIA role so use explicit selector
    r = await extract("You logged into a secure area", page=page, selector="#flash")
    _print_result("Extract flash message", r)
    results.append(r)

    # Step 6 — click Logout
    r = await act("Click Logout", page=page)
    _print_result("Click Logout", r)
    results.append(r)


async def run_fuzzy_match_suite(page, results: list) -> None:
    print("── Fuzzy / Synonym Healing ─────────────────────────────────────")
    await page.goto("https://the-internet.herokuapp.com/login")
    await page.wait_for_load_state("domcontentloaded")

    # "Sign in" is NOT on the page — the button says "Login".
    # FuzzyTextResolver's synonym table maps sign-in → login so this should heal.
    r = await act("Click Sign in", page=page)
    _print_result('Click "Sign in" (healed → Login button)', r)
    results.append(r)


async def run_checkboxes_suite(page, results: list) -> None:
    print("── Checkboxes Page ─────────────────────────────────────────────")
    await page.goto("https://the-internet.herokuapp.com/checkboxes")
    await page.wait_for_load_state("domcontentloaded")

    # The checkboxes page has two unlabeled checkboxes — use CSS selector directly.
    # This is exactly the right use case for explicit selector fallback.
    from bubblegum import act as _act
    r = await _act("Click first checkbox", page=page, selector="input[type='checkbox']:first-of-type")
    _print_result("Click first checkbox (explicit selector)", r)
    results.append(r)


async def run_session_demo(page) -> list:
    """Same login flow using BubblegumSession — no page= on every call."""
    print("── Session API Demo ─────────────────────────────────────────────")
    await page.goto("https://the-internet.herokuapp.com/login")
    await page.wait_for_load_state("domcontentloaded")

    results = []
    async with BubblegumSession.web(page) as s:
        await s.act('Enter "tomsmith" into Username')
        await s.act('Enter "SuperSecretPassword!" into Password')
        await s.act("Click Login")
        await s.verify("You logged into a secure area")
        await s.extract("You logged into a secure area", selector="#flash")
        await s.act("Click Logout")

        for r in s.results():
            _print_result(r.action, r)
            results.append(r)

        summ = s.summary()
        print(f"  Session summary: {summ}\n")

    return results


async def run_dry_run_demo(page) -> None:
    """Show dry_run=True — resolves elements without clicking anything."""
    print("── Dry-Run Demo (resolve only, no execution) ───────────────────")
    await page.goto("https://the-internet.herokuapp.com/login")
    await page.wait_for_load_state("domcontentloaded")

    async with BubblegumSession.web(page, dry_run=True) as s:
        await s.act('Enter "tomsmith" into Username')
        await s.act('Enter "SuperSecretPassword!" into Password')
        await s.act("Click Login")
        s.print_plan()   # shows what would be clicked — no browser changes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(headed: bool, enable_llm: bool) -> int:
    artifacts = Path("artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)

    # Configure bubblegum — deterministic by default, LLM opt-in
    if not enable_llm:
        # Override config to disable AI so no API key is needed.
        cfg = BubblegumConfig.load()
        cfg.ai.enabled = False
        sdk.configure_runtime(config=cfg)
        print("Mode: deterministic-only (no AI/API key needed)")
    else:
        print("Mode: deterministic + LLM fallback (requires OPENAI_API_KEY or bubblegum.yaml)")

    from playwright.async_api import async_playwright

    results: list = []
    failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        page = await browser.new_page()

        try:
            await run_login_suite(page, results)
            await run_secure_page_suite(page, results)
            await run_fuzzy_match_suite(page, results)
            await run_checkboxes_suite(page, results)
            session_results = await run_session_demo(page)
            results.extend(session_results)
            await run_dry_run_demo(page)   # dry_run results not counted in pass/fail
        finally:
            await browser.close()

    # Report
    for r in results:
        if r.status == "failed":
            failed += 1

    print(f"\n── Summary ─────────────────────────────────────────────────────")
    print(f"  Total: {len(results)}   Passed: {len(results) - failed}   Failed: {failed}")

    json_path = write_json_report(results, artifacts / "real-web-test.json", title="Real Web Test")
    html_path = write_html_report(results, artifacts / "real-web-test.html", title="Real Web Test")
    print(f"\n  JSON report: {json_path}")
    print(f"  HTML report: {html_path}")
    print(f"  Open: open {html_path}\n")

    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bubblegum real-web smoke test")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--llm", action="store_true", help="Enable LLM fallback resolver")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(headed=args.headed, enable_llm=args.llm)))
