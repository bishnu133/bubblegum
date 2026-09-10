"""Feature: add multiple items to a token/tags multi-input.

A tags field keeps a typed value in its search box until a keystroke commits it
as a chip; an uncommitted value is overwritten by the next item. The engine now
commits each typed value — via an explicit "… and press Enter/Tab" in the step,
or automatically (Enter) for a token/tags multi-input — and the box clears, so
repeated "Enter X into <field>" steps each add a new item.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a Chromium binary if needed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

# Ant-style multi "tags" input: typing + Enter or Tab commits a chip and clears
# the search box (mirrors rc-select behaviour).
_TAGS_PAGE = r"""
<!doctype html><html><body style="font-family:Helvetica">
<div class="ant-form-item"><div class="ant-form-item-label"><label for="milestones" title="Milestones">Milestones</label></div>
 <div class="ant-select ant-select-multiple ant-select-show-search" data-testid="milestone-select" style="width:800px">
  <div class="ant-select-selector"><span class="ant-select-selection-wrap">
    <div class="ant-select-selection-overflow" id="ovf"></div>
    <div class="ant-select-selection-search" style="width:4px">
      <input id="milestones" autocomplete="off" class="ant-select-selection-search-input" role="combobox"
             aria-expanded="false" aria-haspopup="listbox" aria-owns="milestones_list" aria-autocomplete="list"
             aria-controls="milestones_list" type="search" value=""></div></span></div></div></div>
<script>
 const input=document.getElementById('milestones'), ovf=document.getElementById('ovf');
 function commit(){ const v=input.value.trim(); if(!v) return false;
   const item=document.createElement('div'); item.className='ant-select-selection-overflow-item';
   const tag=document.createElement('span'); tag.className='ant-select-selection-item'; tag.setAttribute('title',v);
   tag.textContent=v; item.append(tag); ovf.append(item); input.value=''; return true; }
 input.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key==='Tab'){ if(commit()) e.preventDefault(); }});
 window.__tags=()=>[...ovf.querySelectorAll('.ant-select-selection-item')].map(t=>t.getAttribute('title'));
</script></body></html>
"""

# A plain single text input inside a form — submitting sets a flag we assert stays false.
_PLAIN_PAGE = """<!doctype html><html><body style="font-family:Helvetica">
<form onsubmit="window.__submitted=true;return false;">
 <label for="name">Full Name</label><input id="name" type="text" value=""></form>
<script>window.__submitted=false;</script></body></html>"""


async def _page(p, html):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(html)
    return browser, page


async def _add_three(step_tpl):
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _TAGS_PAGE)
        try:
            for v in ("AutoM1", "AutoM2", "AutoM3"):
                await act(step_tpl.format(v=v), channel="web", page=page)
            return await page.evaluate("window.__tags()")
        finally:
            await browser.close()


async def test_explicit_press_tab_adds_multiple_items():
    assert await _add_three('Enter "{v}" into Milestones and press Tab') == ["AutoM1", "AutoM2", "AutoM3"]


async def test_explicit_press_enter_adds_multiple_items():
    assert await _add_three('Enter "{v}" into Milestones and press Enter') == ["AutoM1", "AutoM2", "AutoM3"]


async def test_token_input_auto_commits_without_explicit_key():
    # No "press …" directive — a token/tags input still commits each value.
    assert await _add_three('Enter "{v}" into Milestones') == ["AutoM1", "AutoM2", "AutoM3"]


async def test_plain_text_input_is_not_committed():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _PLAIN_PAGE)
        try:
            await act('Enter "John Doe" into Full Name', channel="web", page=page)
            assert await page.eval_on_selector("#name", "e => e.value") == "John Doe"
            # A plain input must NOT receive a stray Enter that submits the form.
            assert await page.evaluate("window.__submitted") is False
        finally:
            await browser.close()
