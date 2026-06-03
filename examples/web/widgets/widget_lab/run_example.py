"""Phase 22D-4: widget lab — native <select> and file upload examples.

Spins up a tiny static HTTP server serving pages/ and drives Bubblegum NL
instructions through Playwright against it. Each scenario verifies widget
*state* (selected value, uploaded file count) in addition to result text.

Run:
    python examples/web/widgets/widget_lab/run_example.py            # headless
    python examples/web/widgets/widget_lab/run_example.py --headed   # visible
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PLAYWRIGHT_INSTALL_HINT = """Playwright is not installed.
Install with:
  pip install -e ".[web]"
Then install browser binaries:
  python -m playwright install chromium
"""

_PAGES_DIR = Path(__file__).resolve().parent / "pages"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    port = _find_free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(_PAGES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def _result(name: str, passed: bool, **detail) -> dict:
    out = {"scenario": name, "passed": passed}
    out.update(detail)
    return out


async def run_select_scenario(page, base_url: str) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/select.html")
    await page.wait_for_load_state("domcontentloaded")

    # NL instruction with explicit selector + value as a safety net so the
    # adapter dispatch path is exercised even when the resolver chain has
    # not yet been wired for accessibility-tree label-for lookup on
    # <select> elements (added in 22D-7).
    step = await act(
        "Select India from Country",
        page=page,
        channel="web",
        action_type="select",
        selector="#country",
        input_value="IN",
    )

    selected_value = await page.locator("#country").input_value()
    state_ok = selected_value == "IN"
    result_text = await page.locator("#result").inner_text()
    text_ok = "India" in result_text

    passed = step.status == "passed" and state_ok and text_ok
    return _result(
        "native-select",
        passed,
        action_status=step.status,
        selected_value=selected_value,
        result_text=result_text,
        state_ok=state_ok,
        text_ok=text_ok,
    )


async def run_upload_scenario(page, base_url: str) -> dict:
    from bubblegum import act

    await page.goto(f"{base_url}/upload.html")
    await page.wait_for_load_state("domcontentloaded")

    tmp = tempfile.NamedTemporaryFile(prefix="widget_lab_resume_", suffix=".pdf", delete=False)
    try:
        tmp.write(b"%PDF-1.4 widget_lab sample resume\n")
        tmp.flush()
        upload_path = tmp.name
    finally:
        tmp.close()

    step = await act(
        f"Upload {upload_path} to Resume",
        page=page,
        channel="web",
        action_type="upload",
        selector="#resume",
        input_value=upload_path,
    )

    has_files = await page.evaluate(
        "() => { const i = document.querySelector('#resume');"
        " return !!(i && i.files && i.files.length); }"
    )
    result_text = await page.locator("#result").inner_text()
    basename = Path(upload_path).name
    text_ok = basename in result_text

    passed = step.status == "passed" and bool(has_files) and text_ok
    return _result(
        "file-upload",
        passed,
        action_status=step.status,
        upload_path=upload_path,
        has_files=bool(has_files),
        result_text=result_text,
        text_ok=text_ok,
    )


async def run(headless: bool) -> int:
    from playwright.async_api import async_playwright

    server, base_url = _start_server()
    print(f"Serving widget lab at {base_url}")

    results: list[dict] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(5_000)

                results.append(await run_select_scenario(page, base_url))
                results.append(await run_upload_scenario(page, base_url))
            finally:
                await browser.close()
    finally:
        server.shutdown()

    print("\nsummary:")
    failed = 0
    for r in results:
        status = "passed" if r["passed"] else "failed"
        print(f"  {r['scenario']:20s} {status}")
        for k, v in r.items():
            if k in {"scenario", "passed"}:
                continue
            print(f"    {k}: {v!r}")
        if not r["passed"]:
            failed += 1
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true", help="Run with a visible browser")
    args = parser.parse_args()

    try:
        return asyncio.run(run(headless=not args.headed))
    except ModuleNotFoundError as exc:
        if "playwright" in str(exc):
            print(PLAYWRIGHT_INSTALL_HINT)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
