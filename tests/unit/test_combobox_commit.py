"""A dropdown pick must be *committed*, not merely dispatched.

Symptom reported from the field: the value is typed into an Ant multi-select's
search box, an option is clicked, the step reports success — yet no tag is
selected. Some virtualised / portalled lists accept the option click as a DOM
event but never commit it. ``_try_pick_option`` now confirms the choice actually
rendered as a selection item (for Ant selects) and, when a click didn't take,
presses Enter to commit the filtered option.

These are browser-gated (skip when no Chromium is available). The page is a
minimal but functional Ant-style multi-select: typing filters options; clicking
an option commits it — unless ``data-block`` is set, which swallows option clicks
(mimicking the miss) while the search box still commits on Enter.
"""
from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter


def _page_html(block: bool) -> str:
    blk = " data-block='1'" if block else ""
    return (
        "<!doctype html><html><body" + blk + ">"
        "<span>Eligibility Tags</span>"
        "<div class='ant-select ant-select-multiple ant-select-show-search' data-testid='tags' style='width:300px'>"
        "  <div class='ant-select-selector'><span class='ant-select-selection-wrap'>"
        "    <div class='ant-select-selection-overflow'></div>"
        "    <span class='ant-select-selection-search'>"
        "      <input class='ant-select-selection-search-input' role='combobox' type='search' id='search'>"
        "    </span></span></div></div>"
        "<div id='dd' class='ant-select-dropdown ant-select-dropdown-hidden' style='position:absolute'></div>"
        "<script>"
        "var OPTIONS=['Aerobic','Anaerobic','Strength'];"
        "var input=document.getElementById('search'),dd=document.getElementById('dd');"
        "var overflow=document.querySelector('.ant-select-selection-overflow');"
        "function selected(){return Array.from(overflow.querySelectorAll('.ant-select-selection-item')).map(function(n){return n.getAttribute('title')});}"
        "function commit(v){if(selected().indexOf(v)>=0)return;var t=document.createElement('div');t.className='ant-select-selection-overflow-item';"
        "t.innerHTML=\"<span class='ant-select-selection-item' title='\"+v+\"'><span class='ant-select-selection-item-content'>\"+v+'</span></span>';"
        "overflow.appendChild(t);input.value='';render();}"
        "function items(){var q=input.value.trim().toLowerCase();return OPTIONS.filter(function(o){return o.toLowerCase().indexOf(q)>=0});}"
        "function render(){var it=items();dd.innerHTML=it.map(function(o,i){return \"<div class='ant-select-item ant-select-item-option\"+(i===0?' ant-select-item-option-active':'')+\"' title='\"+o+\"'><div class='ant-select-item-option-content'>\"+o+'</div></div>'}).join('');"
        "dd.querySelectorAll('.ant-select-item-option').forEach(function(el){el.addEventListener('mousedown',function(e){if(document.body.dataset.block){e.preventDefault();e.stopPropagation();return;}commit(el.getAttribute('title'));});});}"
        "function open(){dd.classList.remove('ant-select-dropdown-hidden');var r=input.getBoundingClientRect();dd.style.left=r.left+'px';dd.style.top=r.bottom+'px';render();}"
        "document.querySelector('.ant-select-selector').addEventListener('click',open);input.addEventListener('focus',open);input.addEventListener('input',render);"
        "input.addEventListener('keydown',function(e){if(e.key==='Enter'){var it=items();if(it.length)commit(it[0]);}});"
        "</script></body></html>"
    )


def _select(block: bool):
    async_api = pytest.importorskip("playwright.async_api")

    async def go():
        try:
            pw = await async_api.async_playwright().start()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright unavailable: {exc}")
        try:
            try:
                browser = await pw.chromium.launch()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No usable browser binary: {exc}")
            try:
                page = await browser.new_page()
                await page.set_content(_page_html(block))
                adapter = PlaywrightAdapter(page)
                trigger = page.locator('[data-testid="tags"]')
                try:
                    await adapter._select_from_custom_combobox(trigger, "Aerobic", 4000)
                except Exception:  # noqa: BLE001 — inspect the committed result below
                    pass
                return await adapter._selected_texts(trigger)
            finally:
                await browser.close()
        finally:
            await pw.stop()

    return asyncio.run(go())


@pytest.mark.playwright
def test_click_path_commits_selection() -> None:
    assert "Aerobic" in _select(block=False)


@pytest.mark.playwright
def test_enter_fallback_commits_when_click_is_swallowed() -> None:
    # The click is dispatched but the widget drops it — the pick must still land
    # via the Enter-to-commit fallback rather than reporting a phantom success.
    assert "Aerobic" in _select(block=True)


# A functional SINGLE-select whose committed label carries an extra affix, so a
# strict value==label check would false-negative. The pick must commit exactly
# once (not re-fire Enter or probe other selects) — the "ran twice" regression.
_SINGLE = (
    "<!doctype html><html><body><label>Division Name</label>"
    "<div class='ant-select ant-select-single ant-select-show-search' data-testid='d' style='width:320px'>"
    "  <div class='ant-select-selector'><span class='ant-select-selection-wrap'>"
    "    <span class='ant-select-selection-search'><input class='ant-select-selection-search-input' role='combobox' type='search' id='s'></span>"
    "    <span class='ant-select-selection-item' title=''></span></span></div></div>"
    "<div id='dd' class='ant-select-dropdown ant-select-dropdown-hidden' style='position:absolute'></div>"
    "<script>window.__commits=0;var OPTIONS=['Fresh Fruits & Vegetables','Team Sports'];"
    "var input=document.getElementById('s'),dd=document.getElementById('dd'),item=document.querySelector('.ant-select-selection-item');"
    "function commit(v){window.__commits++;item.setAttribute('title',v+' (active)');item.textContent=v+' (active)';input.value='';dd.classList.add('ant-select-dropdown-hidden');}"
    "function items(){var q=input.value.trim().toLowerCase();return OPTIONS.filter(function(o){return o.toLowerCase().indexOf(q)>=0});}"
    "function render(){dd.innerHTML=items().map(function(o){return \"<div class='ant-select-item ant-select-item-option' title='\"+o+\"'>\"+o+'</div>'}).join('');"
    "dd.querySelectorAll('.ant-select-item-option').forEach(function(el){el.addEventListener('mousedown',function(){commit(el.getAttribute('title'));});});}"
    "function open(){dd.classList.remove('ant-select-dropdown-hidden');var r=input.getBoundingClientRect();dd.style.left=r.left+'px';dd.style.top=r.bottom+'px';render();}"
    "document.querySelector('.ant-select-selector').addEventListener('click',open);input.addEventListener('focus',open);input.addEventListener('input',render);"
    "input.addEventListener('keydown',function(e){if(e.key==='Enter'){var it=items();if(it.length)commit(it[0]);}});</script></body></html>"
)


@pytest.mark.playwright
def test_multi_select_adds_every_comma_separated_value() -> None:
    # A tags (multi-select) widget takes several values in one step, written
    # comma-separated. Each must be committed as its own tag.
    async_api = pytest.importorskip("playwright.async_api")
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    async def go():
        try:
            pw = await async_api.async_playwright().start()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright unavailable: {exc}")
        try:
            try:
                browser = await pw.chromium.launch()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No usable browser binary: {exc}")
            try:
                page = await browser.new_page()
                await page.set_content(_page_html(block=False))
                adapter = PlaywrightAdapter(page)
                trigger = page.locator('[data-testid="tags"]')
                await adapter._select_from_custom_combobox(trigger, "Aerobic, Strength", 4000)
                return await adapter._selected_texts(trigger)
            finally:
                await browser.close()
        finally:
            await pw.stop()

    sel = asyncio.run(go())
    assert "Aerobic" in sel and "Strength" in sel


_TAGS = (
    "<!doctype html><html><body>"
    "<div class='ant-select ant-select-multiple ant-select-show-search' data-testid='tags' style='width:320px'>"
    "  <div class='ant-select-selector'><span class='ant-select-selection-wrap'><div class='ant-select-selection-overflow'></div>"
    "  <span class='ant-select-selection-search'><input class='ant-select-selection-search-input' role='combobox' type='search' id='s'></span></span></div></div>"
    "<div id='dd' class='ant-select-dropdown ant-select-dropdown-hidden' style='position:absolute'></div>"
    "<script>var OPTIONS=['TagAccepted','BetaApp','TaskLog','Aerobic'];"
    "var input=document.getElementById('s'),dd=document.getElementById('dd'),overflow=document.querySelector('.ant-select-selection-overflow');"
    "function selected(){return Array.from(overflow.querySelectorAll('.ant-select-selection-item')).map(function(n){return n.getAttribute('title')});}"
    "function commit(v){if(selected().indexOf(v)>=0)return;var t=document.createElement('div');t.className='ant-select-selection-overflow-item';t.innerHTML=\"<span class='ant-select-selection-item' title='\"+v+\"'>\"+v+'</span>';overflow.appendChild(t);input.value='';render();}"
    "function items(){var q=input.value.trim().toLowerCase();return OPTIONS.filter(function(o){return o.toLowerCase().indexOf(q)>=0});}"
    "function render(){dd.innerHTML=items().map(function(o){return \"<div class='ant-select-item ant-select-item-option' title='\"+o+\"'>\"+o+'</div>'}).join('');"
    "dd.querySelectorAll('.ant-select-item-option').forEach(function(el){el.addEventListener('mousedown',function(){commit(el.getAttribute('title'));});});}"
    "function open(){dd.classList.remove('ant-select-dropdown-hidden');var r=input.getBoundingClientRect();dd.style.left=r.left+'px';dd.style.top=r.bottom+'px';render();}"
    "document.querySelector('.ant-select-selector').addEventListener('click',open);input.addEventListener('focus',open);input.addEventListener('input',render);"
    "input.addEventListener('keydown',function(e){if(e.key==='Enter'){var it=items();if(it.length)commit(it[0]);}});</script></body></html>"
)


@pytest.mark.playwright
def test_multi_select_tolerates_spacing_difference() -> None:
    # Step says "Task Log"; the option is rendered "TaskLog". All three must land.
    async_api = pytest.importorskip("playwright.async_api")
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    async def go():
        try:
            pw = await async_api.async_playwright().start()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright unavailable: {exc}")
        try:
            try:
                browser = await pw.chromium.launch()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No usable browser binary: {exc}")
            try:
                page = await browser.new_page()
                await page.set_content(_TAGS)
                adapter = PlaywrightAdapter(page)
                trigger = page.locator('[data-testid="tags"]')
                await adapter._select_from_custom_combobox(trigger, "TagAccepted, BetaApp, Task Log", 4000)
                return await adapter._selected_texts(trigger)
            finally:
                await browser.close()
        finally:
            await pw.stop()

    sel = asyncio.run(go())
    assert "TagAccepted" in sel and "BetaApp" in sel and "TaskLog" in sel


@pytest.mark.playwright
def test_inner_combobox_input_trigger_commits_without_probe() -> None:
    # Grounding often resolves a select to its INNER <input role=combobox>. Reading
    # the selection must climb to the .ant-select root, else the commit check
    # false-negatives and the slow other-combobox probe / double Enter kicks in.
    async_api = pytest.importorskip("playwright.async_api")
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    async def go():
        try:
            pw = await async_api.async_playwright().start()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright unavailable: {exc}")
        try:
            try:
                browser = await pw.chromium.launch()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No usable browser binary: {exc}")
            try:
                page = await browser.new_page()
                await page.set_content(_SINGLE)
                adapter = PlaywrightAdapter(page)
                inner = page.locator("#s")   # the <input>, as a11y resolves it
                import time as _t
                t0 = _t.time()
                await adapter._select_from_custom_combobox(inner, "Fresh Fruits & Vegetables", 4000)
                elapsed = _t.time() - t0
                return await page.evaluate("window.__commits"), elapsed
            finally:
                await browser.close()
        finally:
            await pw.stop()

    commits, elapsed = asyncio.run(go())
    assert commits == 1, f"expected a single commit, got {commits}"
    assert elapsed < 10, f"should not fall into the slow probe (took {elapsed:.1f}s)"


@pytest.mark.playwright
def test_single_select_commits_once_when_label_has_affix() -> None:
    async_api = pytest.importorskip("playwright.async_api")
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    async def go():
        try:
            pw = await async_api.async_playwright().start()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Playwright unavailable: {exc}")
        try:
            try:
                browser = await pw.chromium.launch()
            except Exception as exc:  # pragma: no cover
                pytest.skip(f"No usable browser binary: {exc}")
            try:
                page = await browser.new_page()
                await page.set_content(_SINGLE)
                adapter = PlaywrightAdapter(page)
                trigger = page.locator('[data-testid="d"]')
                await adapter._select_from_custom_combobox(trigger, "Fresh Fruits & Vegetables", 4000)
                commits = await page.evaluate("window.__commits")
                sel = await adapter._selected_texts(trigger)
                return commits, sel
            finally:
                await browser.close()
        finally:
            await pw.stop()

    commits, sel = asyncio.run(go())
    assert commits == 1, f"expected a single commit, got {commits} (double-run regression)"
    assert sel and "Fresh Fruits & Vegetables" in sel[0]
