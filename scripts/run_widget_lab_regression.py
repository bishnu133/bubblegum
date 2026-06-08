#!/usr/bin/env python3
"""Phase 22D-9: Tier 1 widget regression runner.

Runs every Bubblegum widget-lab scenario back-to-back, captures pass/fail
and per-scenario detail, writes a structured JSON report to
artifacts/widget_lab_regression.json, and prints a summary table. Exits
non-zero when any scenario fails.

Default: lab only (no external network).
With --public: also runs the matching subset against
the-internet.herokuapp.com (login, dropdown, checkboxes, upload) as a
public-site smoke. Opt-in because the public site is not always reachable.

Usage:
  python scripts/run_widget_lab_regression.py
  python scripts/run_widget_lab_regression.py --strict     # NL-only mode
  python scripts/run_widget_lab_regression.py --public
  python scripts/run_widget_lab_regression.py --headed
  python scripts/run_widget_lab_regression.py --json /tmp/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with:
  pip install -e ".[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_RUNNER = _REPO_ROOT / "examples" / "web" / "widgets" / "widget_lab" / "run_example.py"
_DEFAULT_JSON = _REPO_ROOT / "artifacts" / "widget_lab_regression.json"


# ---------------------------------------------------------------------------
# Lab scenario import (shared with examples/.../run_example.py)
# ---------------------------------------------------------------------------


def _import_lab_module():
    spec = importlib.util.spec_from_file_location("widget_lab_runner", _LAB_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load widget lab runner from {_LAB_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Public-site scenarios (the-internet.herokuapp.com smoke)
# ---------------------------------------------------------------------------

_PUBLIC_BASE = "https://the-internet.herokuapp.com"


async def public_login(page) -> dict[str, Any]:
    from bubblegum import act

    await page.goto(f"{_PUBLIC_BASE}/login")
    await page.wait_for_load_state("domcontentloaded")

    s_user = await act(
        'Enter "tomsmith" into Username',
        page=page,
        channel="web",
        action_type="type",
        selector='input[name="username"]',
        input_value="tomsmith",
    )
    s_pass = await act(
        'Enter "SuperSecretPassword!" into Password',
        page=page,
        channel="web",
        action_type="type",
        selector='input[name="password"]',
        input_value="SuperSecretPassword!",
    )
    s_click = await act(
        "Click Login",
        page=page,
        channel="web",
        action_type="click",
        selector="button[type='submit']",
    )

    await page.wait_for_selector("#flash", timeout=5000)
    flash = (await page.locator("#flash").inner_text()).strip()
    state_ok = "You logged into a secure area" in flash

    passed = all(s.status == "passed" for s in (s_user, s_pass, s_click)) and state_ok
    return {
        "scenario": "public-login",
        "passed": passed,
        "username_status": s_user.status,
        "password_status": s_pass.status,
        "click_status": s_click.status,
        "flash_excerpt": flash[:80],
    }


async def public_dropdown(page) -> dict[str, Any]:
    from bubblegum import act

    await page.goto(f"{_PUBLIC_BASE}/dropdown")
    await page.wait_for_load_state("domcontentloaded")

    step = await act(
        "Select Option 2 from Dropdown List",
        page=page,
        channel="web",
        action_type="select",
        selector="#dropdown",
        input_value="2",
    )
    selected = await page.locator("#dropdown").input_value()
    passed = step.status == "passed" and selected == "2"
    return {
        "scenario": "public-dropdown",
        "passed": passed,
        "action_status": step.status,
        "selected_value": selected,
    }


async def public_checkboxes(page) -> dict[str, Any]:
    from bubblegum import act

    await page.goto(f"{_PUBLIC_BASE}/checkboxes")
    await page.wait_for_load_state("domcontentloaded")

    step_check = await act(
        "Check first checkbox",
        page=page,
        channel="web",
        action_type="check",
        selector="input[type='checkbox']:nth-of-type(1)",
    )
    step_uncheck = await act(
        "Uncheck second checkbox",
        page=page,
        channel="web",
        action_type="uncheck",
        selector="input[type='checkbox']:nth-of-type(2)",
    )
    first_checked = await page.locator("input[type='checkbox']:nth-of-type(1)").is_checked()
    second_unchecked = not await page.locator("input[type='checkbox']:nth-of-type(2)").is_checked()
    passed = (
        step_check.status == "passed"
        and step_uncheck.status == "passed"
        and first_checked
        and second_unchecked
    )
    return {
        "scenario": "public-checkboxes",
        "passed": passed,
        "check_status": step_check.status,
        "uncheck_status": step_uncheck.status,
        "first_checked": first_checked,
        "second_unchecked": second_unchecked,
    }


async def public_upload(page) -> dict[str, Any]:
    from bubblegum import act

    await page.goto(f"{_PUBLIC_BASE}/upload")
    await page.wait_for_load_state("domcontentloaded")

    tmp = tempfile.NamedTemporaryFile(
        prefix="bubblegum_public_upload_", suffix=".txt", delete=False
    )
    try:
        tmp.write(b"phase 22D-9 regression upload\n")
        tmp.flush()
        upload_path = tmp.name
    finally:
        tmp.close()

    step_upload = await act(
        f"Upload {upload_path} to file upload",
        page=page,
        channel="web",
        action_type="upload",
        selector="#file-upload",
        input_value=upload_path,
    )
    step_submit = await act(
        "Click file submit",
        page=page,
        channel="web",
        action_type="click",
        selector="#file-submit",
    )
    await page.wait_for_load_state("domcontentloaded")
    body = await page.locator("body").inner_text()
    basename = Path(upload_path).name
    state_ok = "File Uploaded!" in body and basename in body
    passed = step_upload.status == "passed" and step_submit.status == "passed" and state_ok
    return {
        "scenario": "public-upload",
        "passed": passed,
        "upload_status": step_upload.status,
        "submit_status": step_submit.status,
        "file_uploaded": "File Uploaded!" in body,
        "filename_present": basename in body,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _timed(coro: Awaitable[dict[str, Any]], *, source: str) -> dict[str, Any]:
    t0 = time.monotonic()
    try:
        result = await coro
    except Exception as exc:  # noqa: BLE001 — capture for the report
        result = {
            "scenario": "<exception>",
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    result["source"] = source
    return result


async def _run_lab(headless: bool, *, nl_only: bool = False) -> list[dict[str, Any]]:
    lab = _import_lab_module()
    from playwright.async_api import async_playwright

    server, base_url = lab._start_server()
    results: list[dict[str, Any]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(5_000)
                for fn in (
                    lab.run_select_scenario,
                    lab.run_upload_scenario,
                    lab.run_checkbox_scenario,
                    lab.run_radio_scenario,
                    lab.run_link_vs_button_scenario,
                    lab.run_combobox_scenario,
                    lab.run_modal_scenario,
                ):
                    results.append(await _timed(fn(page, base_url, nl_only=nl_only), source="lab"))
            finally:
                await browser.close()
    finally:
        server.shutdown()
    return results


async def _run_public(headless: bool) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    scenarios: list[Callable[[Any], Awaitable[dict[str, Any]]]] = [
        public_login,
        public_dropdown,
        public_checkboxes,
        public_upload,
    ]
    results: list[dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(8_000)  # public site can be slower
            for fn in scenarios:
                results.append(await _timed(fn(page), source="public"))
        finally:
            await browser.close()
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_summary(results: list[dict[str, Any]]) -> int:
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total_ms = sum(r.get("duration_ms", 0) for r in results)

    print()
    print("Bubblegum Phase 22D — Tier 1 Widget Regression")
    print("=" * 64)
    print(f"{'SOURCE':<8} {'SCENARIO':<22} {'STATUS':<10} {'DURATION':>10}")
    print("-" * 64)
    for r in results:
        status = "passed" if r["passed"] else "FAILED"
        dur = f"{r.get('duration_ms', 0)}ms"
        print(f"{r.get('source','?'):<8} {r['scenario']:<22} {status:<10} {dur:>10}")
    print("-" * 64)
    print(f"{passed} passed, {failed} failed   (total {total_ms / 1000:.1f}s)")

    if failed:
        print()
        print("Failures (per-scenario detail):")
        for r in results:
            if r["passed"]:
                continue
            print(f"  {r['source']}/{r['scenario']}:")
            for k, v in r.items():
                if k in {"source", "scenario", "passed"}:
                    continue
                print(f"    {k}: {v!r}")

    return 0 if failed == 0 else 1


def _write_json(results: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": "22D-9",
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "total_duration_ms": sum(r.get("duration_ms", 0) for r in results),
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run(args: argparse.Namespace) -> int:
    headless = not args.headed
    results: list[dict[str, Any]] = []

    results.extend(await _run_lab(headless=headless, nl_only=args.strict))
    if args.public:
        try:
            results.extend(await _run_public(headless=headless))
        except Exception as exc:  # noqa: BLE001 — record and continue
            results.append({
                "source": "public",
                "scenario": "<setup-failed>",
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "duration_ms": 0,
            })

    _write_json(results, Path(args.json) if args.json else _DEFAULT_JSON)
    return _print_summary(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public", action="store_true", help="Also run public-site smoke")
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser")
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Strict NL-only mode for lab scenarios: drop selector= / "
            "action_type= / input_value= and let the parser + resolver work."
        ),
    )
    parser.add_argument(
        "--json",
        default=None,
        help=f"Path to write JSON report (default: {_DEFAULT_JSON})",
    )
    args = parser.parse_args()

    try:
        return asyncio.run(_run(args))
    except ModuleNotFoundError as exc:
        if "playwright" in str(exc):
            print(PLAYWRIGHT_INSTALL_HINT)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
