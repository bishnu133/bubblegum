"""Regression: searchable-combobox filtering.

A searchable Ant select renders a filtered / virtualized option list — the
target row is not in the DOM until the user types. The custom-combobox path must
type the value into the search box before clicking the option. Drives real DOM +
event handlers, so it skips when no browser is available.
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
            return await page.locator("#committed").text_content()
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


# Two functional selects: the resolved (primary) one does NOT offer the value;
# a neighbouring one does. The "wrong" one also mimics the Ant quirk of
# auto-selecting its first option on blur — so the test proves the selection both
# self-corrects to the right select AND leaves the wrong one untouched.
_TWO_SELECTS = """
<div class="ant-select ant-select-multiple ant-select-show-search" data-testid="wrong" data-bg-select="1"
     style="width:280px" data-opts="Test Challenge 1234|EDSH Challenge">
  <div class="ant-select-selector"><span class="ant-select-selection-wrap">
    <div class="ant-select-selection-overflow"></div>
    <span class="ant-select-selection-search">
      <input class="ant-select-selection-search-input" role="combobox" type="search"></span></span></div>
</div>
<span>Eligibility Tags</span>
<div class="ant-select ant-select-multiple ant-select-show-search" data-testid="right"
     style="width:280px" data-opts="ADBetaUser|FeelingHealthy|GaqAccepted">
  <div class="ant-select-selector"><span class="ant-select-selection-wrap">
    <div class="ant-select-selection-overflow"></div>
    <span class="ant-select-selection-search">
      <input class="ant-select-selection-search-input" role="combobox" type="search"></span></span></div>
</div>
<div id="committed">none</div>
<script>
  document.querySelectorAll('.ant-select').forEach(sel=>{
    const inp=sel.querySelector('input'); const overflow=sel.querySelector('.ant-select-selection-overflow'); let dd=null;
    const opts=()=>sel.getAttribute('data-opts').split('|');
    function addTag(o){ if([...overflow.querySelectorAll('.ant-select-selection-item')].some(n=>n.title===o))return;
      const it=document.createElement('div'); it.className='ant-select-selection-overflow-item';
      it.innerHTML='<span class="ant-select-selection-item" title="'+o+'"><span class="ant-select-selection-item-content">'+o+'</span><span class="ant-select-selection-item-remove">x</span></span>';
      it.querySelector('.ant-select-selection-item-remove').addEventListener('mousedown',(e)=>{e.preventDefault();e.stopPropagation();it.remove();});
      overflow.appendChild(it); }
    function open(){ if(dd) dd.remove(); dd=document.createElement('div'); dd.className='ant-select-dropdown'; document.body.appendChild(dd); render(''); }
    function render(q){ dd.innerHTML='';
      opts().filter(o=>!q||o.toLowerCase().includes(q.toLowerCase())).forEach(o=>{
        const d=document.createElement('div'); d.className='ant-select-item ant-select-item-option'; d.title=o;
        d.innerHTML='<div class="ant-select-item-option-content">'+o+'</div>';
        d.addEventListener('mousedown',(e)=>{e.preventDefault();addTag(o);document.getElementById('committed').textContent='SEL:'+sel.getAttribute('data-testid')+':'+o;if(dd)dd.remove();dd=null;});
        dd.appendChild(d); }); }
    sel.addEventListener('click',open);
    inp.addEventListener('input',()=>{ if(!dd) open(); render(inp.value); });
    inp.addEventListener('blur',()=>{ if(sel.getAttribute('data-testid')==='wrong'){ addTag(opts()[0]); } if(dd){dd.remove();dd=null;} });
  });
</script>
"""


@pytest.mark.playwright
def test_combobox_self_corrects_and_leaves_wrong_select_untouched() -> None:
    async def drive(adapter, page):
        plan = ActionPlan(action_type="select", target_hint="Eligibility Tags",
                          input_value="GaqAccepted", options=ExecutionOptions())
        await adapter._do_select(plan, page.locator('[data-bg-select="1"]'), 5000)
        wrong = await page.locator('[data-testid=wrong] .ant-select-selection-item').evaluate_all(
            "ns => ns.map(n => n.getAttribute('title'))"
        )
        # The mis-scored select must end up with NO stray selection.
        assert wrong == [], f"wrong select left with stray selection: {wrong}"

    assert asyncio.run(_run(_TWO_SELECTS, drive)) == "SEL:right:GaqAccepted"
