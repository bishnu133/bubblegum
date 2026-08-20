"""A failed step attaches a screenshot artifact (so the report shows the screen).

The success path always screenshots; failures used to return with no artifact, so
the HTML/Allure report had no image for the step that actually failed. `act` and
`verify` now capture a screenshot on failure and attach it as an ArtifactRef.

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

_PAGE = "<!doctype html><html><body style='font-family:Helvetica'><h1>Home</h1></body></html>"


async def _page(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(_PAGE)
    return browser, page


async def test_failed_click_attaches_screenshot():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act('Click the "Nonexistent Zqxw" button', channel="web", page=page)
            assert res.status == "failed"
            shots = [a for a in (res.artifacts or []) if getattr(a, "type", None) == "screenshot"]
            assert shots, "no screenshot artifact attached to the failed step"
            assert Path(shots[0].path).is_file(), f"screenshot file missing: {shots[0].path}"
        finally:
            await browser.close()


async def test_failed_verify_attaches_screenshot():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import verify, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            # Page header is "Home"; asserting a different one fails → screenshot.
            res = await verify('the page header is "Dashboard"', channel="web", page=page)
            assert res.status == "failed"
            shots = [a for a in (res.artifacts or []) if getattr(a, "type", None) == "screenshot"]
            assert shots, "no screenshot artifact attached to the failed header assertion"
            assert Path(shots[0].path).is_file()
        finally:
            await browser.close()


async def test_passed_step_keeps_single_success_screenshot():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import verify, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await verify('the page header is "Home"', channel="web", page=page)
            assert res.status == "passed"
            # A passing page-scoped verify doesn't add a failure screenshot.
            shots = [a for a in (res.artifacts or []) if getattr(a, "type", None) == "screenshot"]
            assert not shots
        finally:
            await browser.close()
