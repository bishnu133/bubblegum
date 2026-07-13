"""Regression: searchable-combobox filtering and datetime-picker OK commit.

Two behaviours that only surface against a *live* widget:

1. A searchable Ant select renders a filtered / virtualized option list — the
   target row is not in the DOM until the user types. The custom-combobox path
   must type the value into the search box before clicking the option.
2. An Ant datetime range picker keeps its panel open with an OK button; Enter
   alone does not commit the value, so ``type`` must click OK when one is shown.

Both drive real DOM + event handlers, so they skip when no browser is available.
"""
from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions


# Options render ONLY after typing — mimics a virtualized/filtered Ant select.
_COMBO = """
<div class="ant-select ant-select-multiple ant-select-show-search" data-testid="v" data-bg-select="1" style="width:300px">
  <div class="ant-select-selector"><span class="ant-select-selection-search">
    <input class="ant-select-selection-search-input" role="combobox" type="search" id="s"></span></div>
  <span class="ant-select-arrow">v</span>
</div>
<div id="dropdown" class="ant-select-dropdown" style="display:none"></div>
<div id="committed">none</div>
<script>
  const ALL=["ADBetaUser","EDSH Pilot A","FeelingHealthy","GaqAccepted","Grandparent"];
  const inp=document.getElementById('s'), dd=document.getElementById('dropdown');
  document.querySelector('.ant-select').addEventListener('click',()=>{dd.style.display='block';render('');});
  inp.addEventListener('input',()=>render(inp.value));
  function render(q){ dd.innerHTML='';
    ALL.filter(o=>!q||o.toLowerCase().includes(q.toLowerCase())).forEach(o=>{
      const d=document.createElement('div'); d.className='ant-select-item ant-select-item-option'; d.title=o;
      d.innerHTML='<div class="ant-select-item-option-content">'+o+'</div>';
      d.addEventListener('mousedown',(e)=>{e.preventDefault();document.getElementById('committed').textContent='SEL:'+o;dd.style.display='none';});
      dd.appendChild(d); }); }
</script>
"""

_PICKER = """
<div class="ant-picker ant-picker-range">
  <div class="ant-picker-input"><input data-bg-daterange="1" date-range="start" placeholder="Start date"></div>
  <div class="ant-picker-input"><input date-range="end" placeholder="End date"></div>
</div>
<div class="ant-picker-footer"><ul class="ant-picker-ranges"><li class="ant-picker-ok"><button type="button"><span>OK</span></button></li></ul></div>
<div id="ok">no</div>
<script>document.querySelector('.ant-picker-ok button').addEventListener('click',()=>{
  document.getElementById('ok').textContent='OK:'+document.querySelector('[data-bg-daterange]').value;});</script>
"""


async def _run(html: str, drive) -> str:
    async_api = pytest.importorskip("playwright.async_api")
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
            await page.set_content(html)
            adapter = PlaywrightAdapter(page)
            await drive(adapter, page)
            return await page.locator("#committed, #ok").last.text_content()
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.mark.playwright
def test_searchable_combobox_types_to_filter_then_selects() -> None:
    async def drive(adapter, page):
        plan = ActionPlan(action_type="select", target_hint="v", input_value="GaqAccepted",
                          options=ExecutionOptions())
        await adapter._do_select(plan, page.locator('[data-bg-select="1"]'), 5000)

    assert asyncio.run(_run(_COMBO, drive)) == "SEL:GaqAccepted"


@pytest.mark.playwright
def test_datetime_picker_clicks_ok_to_commit() -> None:
    async def drive(adapter, page):
        plan = ActionPlan(action_type="type", target_hint="start", input_value="2026/07/15 00:00",
                          options=ExecutionOptions())
        await adapter._do_type(plan, page.locator('[data-bg-daterange="1"]'), 5000)

    assert asyncio.run(_run(_PICKER, drive)) == "OK:2026/07/15 00:00"
