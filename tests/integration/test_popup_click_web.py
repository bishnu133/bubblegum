"""Feature: a click step prefers the button inside an open floating popup.

A table column's filter panel (Ant ``.ant-dropdown`` / ``.ant-table-filter-dropdown``)
carries its own "Search" and "Reset" buttons, and the page usually has a "Search"
button too. The panel is not a modal (no mask, no aria-modal), so the dialog scope
never applied and "Click the Search button" hit the page button instead. An open,
floating popup's exact-name button now wins; the page button still wins when no
popup is open or the popup has no such button.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a Chromium binary if needed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]


def _panel(col: str, *, hidden: bool, top: int, left: int) -> str:
    cls = "ant-dropdown ant-dropdown-placement-bottomRight" + (" ant-dropdown-hidden" if hidden else "")
    style = f"position:absolute;top:{top}px;left:{left}px;z-index:1050;background:#fff;"
    if hidden:
        style += "display:none;"
    return (
        f'<div><div class="{cls}" style="{style}"><div class="ant-table-filter-dropdown">'
        f'<div style="padding:8px"><input placeholder="Search {col}" type="text" style="width:188px;display:block"/>'
        f'<div class="ant-space"><div class="ant-space-item">'
        f'<button type="button" class="ant-btn ant-btn-primary" data-log="{col}:Search">'
        f'<span role="img" aria-label="search" class="anticon anticon-search"><svg width="1em" height="1em"></svg></span>'
        f'<span>Search</span></button></div>'
        f'<div class="ant-space-item"><button type="button" class="ant-btn" data-log="{col}:Reset">'
        f'<span>Reset</span></button></div></div></div></div></div></div>'
    )


_LOG = """<script>window.__clicks=[];
document.querySelectorAll('[data-log]').forEach(el=>el.addEventListener('click',()=>
  window.__clicks.push(el.getAttribute('data-log'))));</script>"""

_PAGE = """
<div style="padding:20px">
 <button type="button" class="ant-btn ant-btn-primary" data-log="PAGE:Search"><span>Search</span></button>
 <button type="button" class="ant-btn" data-log="PAGE:Clear"><span>Clear</span></button>
 <ul role="menu" class="ant-menu ant-menu-horizontal"><li role="menuitem">Reports</li></ul>
 <table><thead><tr>
  <th>Title <span role="button" class="ant-table-filter-trigger"><span role="img" aria-label="search"></span></span></th>
  <th>Updated By <span role="button" class="ant-table-filter-trigger"><span role="img" aria-label="search"></span></span></th>
 </tr></thead><tbody><tr><td>a</td><td>b</td></tr></tbody></table>
</div>"""

# Title panel opened earlier and closed (hidden), Updated By panel open now.
_OPEN = ("<!doctype html><html><body>" + _PAGE
         + _panel("Title", hidden=True, top=200, left=20)
         + _panel("Updated By", hidden=False, top=200, left=300) + _LOG + "</body></html>")
# Both panels closed.
_CLOSED = ("<!doctype html><html><body>" + _PAGE
           + _panel("Title", hidden=True, top=200, left=20)
           + _panel("Updated By", hidden=True, top=200, left=300) + _LOG + "</body></html>")
# Open popup whose button only partly matches the page button's name.
_PARTIAL = ("<!doctype html><html><body>"
            '<button type="button" data-log="PAGE:Save"><span>Save</span></button>'
            '<div class="ant-popover" style="position:absolute;top:120px;left:20px;z-index:1030">'
            '<button type="button" data-log="POP:Save draft">Save draft</button></div>'
            + _LOG + "</body></html>")


async def _clicks(html, step):
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            res = await act(step, channel="web", page=page)
            return res, await page.evaluate("window.__clicks")
        finally:
            await browser.close()


@pytest.mark.parametrize(
    "step,expected",
    [
        ("Click the Search button", ["Updated By:Search"]),
        ("Click on Search", ["Updated By:Search"]),
        ('Click on "Search" button', ["Updated By:Search"]),
        ("Click the Reset button", ["Updated By:Reset"]),
    ],
)
async def test_open_filter_popup_button_wins(step, expected):
    res, clicks = await _clicks(_OPEN, step)
    assert res.status == "passed", res.error
    assert clicks == expected
    assert res.target.resolver_name == "dialog_click_dom"


async def test_page_button_when_popup_lacks_it():
    res, clicks = await _clicks(_OPEN, "Click the Clear button")
    assert res.status == "passed", res.error
    assert clicks == ["PAGE:Clear"]


async def test_page_button_when_no_popup_open():
    res, clicks = await _clicks(_CLOSED, "Click the Search button")
    assert res.status == "passed", res.error
    assert clicks == ["PAGE:Search"]
    assert res.target.resolver_name != "dialog_click_dom"


async def test_popup_needs_whole_name_match():
    res, clicks = await _clicks(_PARTIAL, "Click the Save button")
    assert res.status == "passed", res.error
    assert clicks == ["PAGE:Save"]
