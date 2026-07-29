"""Feature: click a clickable table row by its visible cell text.

Data tables often make the whole row clickable (Ant `onRow` onClick / a
`clickable-row` class / `cursor:pointer`) while the cell content is a plain,
non-interactive `<span>`. The interactive-element resolvers never see that span,
so `Click "<row text>"` used to fail. The clickable-resolver now falls back to a
clickable row whose cell text matches — preferring an exact cell match so a
filtered row isn't confused with a sibling that shares its prefix.

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter


def _table(names: list[str]) -> str:
    rows = "".join(
        f'<tr class="ant-table-row clickable-row" data-row-key="k{i}" data-t="{n}">'
        f'<td class="ant-table-cell"><span style="color:rgb(24,144,255)"> {n} </span></td>'
        f'<td class="ant-table-cell"><span>Enabled</span></td></tr>'
        for i, n in enumerate(names)
    )
    return (
        "<!doctype html><html><body><table><tbody class='ant-table-tbody'>"
        + rows
        + "</tbody></table><script>window.__c='';"
        "document.querySelectorAll('tr[data-row-key]').forEach(r=>"
        "r.addEventListener('click',()=>window.__c=r.getAttribute('data-t')));"
        "</script></body></html>"
    )


async def _click(names, instr):
    aw = pytest.importorskip("playwright.async_api")
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    from bubblegum import act, configure_runtime
    configure_runtime()
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_table(names))
            res = await act(instr, channel="web", page=page)
            clicked = await page.evaluate("window.__c")
            return res.status, clicked
        finally:
            await browser.close()


async def test_click_row_by_quoted_text_single_row():
    status, clicked = await _click(
        ["AutoRoadshow-20260729183240"], 'Click "AutoRoadshow-20260729183240"'
    )
    assert status in ("passed", "recovered")
    assert clicked == "AutoRoadshow-20260729183240"


async def test_click_row_exact_match_among_prefix_siblings():
    """Exact cell match must pick the right row, not a prefix-sharing sibling."""
    names = ["AutoRoadshow-20260729183240", "AutoRoadshow-20260729184224", "gjhdgsaj"]
    status, clicked = await _click(
        names, 'Click the "AutoRoadshow-20260729184224" text in the table'
    )
    assert status in ("passed", "recovered")
    assert clicked == "AutoRoadshow-20260729184224"
