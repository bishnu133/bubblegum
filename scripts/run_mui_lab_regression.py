#!/usr/bin/env python3
"""Phase 22E-4: MUI lab regression runner.

Drives the 4 MUI lab scenarios (select / checkbox / dialog / autocomplete)
back-to-back, writes a structured JSON report to
``artifacts/mui_lab_regression.json``, and prints a summary table.

Usage:
  python scripts/run_mui_lab_regression.py
  python scripts/run_mui_lab_regression.py --strict     # NL-only mode
  python scripts/run_mui_lab_regression.py --headed
  python scripts/run_mui_lab_regression.py --json /tmp/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Awaitable

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with:
  pip install -e ".[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAB_RUNNER = _REPO_ROOT / "examples" / "web" / "widgets" / "mui_lab" / "run_example.py"
_DEFAULT_JSON = _REPO_ROOT / "artifacts" / "mui_lab_regression.json"


def _import_lab_module():
    spec = importlib.util.spec_from_file_location("mui_lab_runner", _LAB_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load MUI lab runner from {_LAB_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
                    lab.run_checkbox_scenario,
                    lab.run_dialog_scenario,
                    lab.run_autocomplete_scenario,
                ):
                    results.append(await _timed(fn(page, base_url, nl_only=nl_only), source="mui"))
            finally:
                await browser.close()
    finally:
        server.shutdown()
    return results


def _print_summary(results: list[dict[str, Any]]) -> int:
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total_ms = sum(r.get("duration_ms", 0) for r in results)

    print()
    print("Bubblegum Phase 22E-4 — MUI Lab Regression")
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
        "phase": "22E-4",
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "total_duration_ms": sum(r.get("duration_ms", 0) for r in results),
        "results": results,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nReport written: {path}")


async def _run(args: argparse.Namespace) -> int:
    results = await _run_lab(headless=not args.headed, nl_only=args.strict)
    _write_json(results, Path(args.json) if args.json else _DEFAULT_JSON)
    return _print_summary(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict NL-only mode: drop selector= / action_type= / input_value= safety nets.",
    )
    parser.add_argument("--json", default=None, help=f"Path to write JSON report (default: {_DEFAULT_JSON})")
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
