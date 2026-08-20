"""A click intercepted by a sticky header still fires (dispatch fallback).

Reproduces the CI failure where `Click on the My Account menu` resolved but the
click timed out because a fixed `<header>` overlays the menu item's hit point
("<header> intercepts pointer events"). The engine now falls back to dispatching
the click event straight at the element, so the menu's handler fires.

Runs against a real (headless) browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

# A fixed header overlays a menu item pinned at the very top — a normal click on
# the item is intercepted by the header (higher z-index over the same point).
_PAGE = """
<!doctype html><html><head><style>
  body { margin:0; font-family:Helvetica; }
  header.ant-layout-header { position:fixed; top:0; left:0; right:0; height:64px;
                             background:#e2e8f0; z-index:1000; }
  .ant-menu-submenu-title { position:absolute; top:16px; left:60%; z-index:1;
                            padding:8px 12px; cursor:pointer; }
</style></head><body>
  <header class="ant-layout-header">Portal Header</header>
  <div role="menuitem" tabindex="-1" aria-haspopup="true" aria-expanded="false"
       class="ant-menu-submenu-title"
       onclick="document.getElementById('out').textContent='opened';">
    <span class="ant-menu-title-content">My Account</span>
  </div>
  <div id="out" style="margin-top:120px">closed</div>
</body></html>
"""


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


async def test_click_menu_under_sticky_header():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act("Click on the My Account menu", channel="web", page=page)
            assert res.status in ("passed", "recovered"), res.error and res.error.message
            assert await page.eval_on_selector("#out", "e => e.textContent") == "opened"
        finally:
            await browser.close()
