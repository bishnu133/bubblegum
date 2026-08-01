"""Feature: verify an item's status shown as a pill/tag/badge/chip — framework
agnostic, no selector. Covers Ant, MUI, Bootstrap, ARIA, and a plain-text
fallback so any tech stack validates.

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]


async def _verify(html, phrase):
    aw = pytest.importorskip("playwright.async_api")
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    from bubblegum import verify, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            return await verify(phrase, channel="web", page=page)
        finally:
            await browser.close()


_ANT = '<div><span class="ant-page-header-heading-sub-title"><span class="ant-tag ant-tag-default">In Draft</span></span></div>'
_MUI = '<div class="MuiChip-root"><span class="MuiChip-label">Published</span></div>'
_BOOTSTRAP = '<span class="badge badge-success">Active</span>'
_ARIA = '<div role="status">Completed</div>'
_PLAIN = '<div class="workout-header"><h2>My Item</h2><small>Archived</small></div>'


async def test_ant_tag_status_passes():
    res = await _verify(_ANT, "the Workouts tag appeared as In Draft")
    assert res.status == "passed"


async def test_ant_tag_wrong_status_fails_with_actual():
    res = await _verify(_ANT, "the Workouts tag appeared as Live")
    assert res.status == "failed"
    assert "In Draft" in (res.error.message if res.error else "")


async def test_mui_chip_status_passes():
    res = await _verify(_MUI, "the status is Published")
    assert res.status == "passed"


async def test_bootstrap_badge_status_passes():
    res = await _verify(_BOOTSTRAP, "the badge shows Active")
    assert res.status == "passed"


async def test_aria_role_status_passes():
    res = await _verify(_ARIA, 'the status is "Completed"')
    assert res.status == "passed"


async def test_plain_text_status_falls_back_and_passes():
    # No status-classed component — the plain-text fallback still validates.
    res = await _verify(_PLAIN, "the item state is Archived")
    assert res.status == "passed"
