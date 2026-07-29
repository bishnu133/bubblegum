"""Regression + feature: `select_no_filter` opts out of type-to-filter.

Some searchable comboboxes key their options by an id/GUID (the option *value*)
while showing a friendly label. Ant filters by the value, so typing the label
empties the list and the option can never be clicked. `select_no_filter=True`
skips the typing and scans (scrolling) the open list instead.

Runs against a real browser; skips when none is available. Set
`BG_CHROMIUM_EXECUTABLE` to point at a Chromium binary if needed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

_OPTS = [
    ("40d5fffc-c4ec-4000-ba14-bdbdeaa8001a", "Alpha Item"),
    ("877f8f7e-dc2a-46ee-b5dc-3731e07c59f3", "Beta Item"),
    ("db8df6f7-846c-434c-9177-b5440e50510a", "Gamma Item"),
    ("aaaa1111-2222-3333-4444-555566667777", "Target-20240101-999"),  # target
]
_ROWS = "".join(
    f'<div name="itemId" data-value="{g}" class="ant-select-item ant-select-item-option">'
    f'<div class="ant-select-item-option-content"><span aria-label="option-{g}">{lbl}</span></div></div>'
    for g, lbl in _OPTS
)
_DOM = ("""
<!doctype html><html><body>
<label for="itemIds" title="Item name">Item name</label>
<div class="ant-select ant-select-multiple ant-select-show-search" data-testid="select-items">
  <div class="ant-select-selector"><span class="ant-select-selection-wrap" id="wrap">
    <div class="ant-select-selection-overflow"><div class="ant-select-selection-search">
      <input id="itemIds" class="ant-select-selection-search-input" role="combobox"
             aria-label="Item name" aria-expanded="false" aria-owns="sch_list"
             aria-controls="sch_list" type="search" value=""></div></div>
    <span class="ant-select-selection-placeholder"></span></span></div>
  <span class="ant-select-arrow"><span aria-label="down">v</span></span></div>
<div><div class="ant-select-dropdown ant-select-dropdown-hidden" id="dd"><div>
  <div role="listbox" id="sch_list" style="height:0;width:0;overflow:hidden"></div>
  <div class="rc-virtual-list"><div class="rc-virtual-list-holder" style="max-height:120px;overflow-y:auto">
    <div class="rc-virtual-list-holder-inner">__ROWS__</div></div></div>
</div></div></div>
<script>
 const sel=document.querySelector('.ant-select'),dd=document.getElementById('dd'),
   input=document.getElementById('itemIds'),wrap=document.getElementById('wrap');
 const rows=[...document.querySelectorAll('.ant-select-item-option')];
 function open(){dd.classList.remove('ant-select-dropdown-hidden');input.setAttribute('aria-expanded','true');}
 function close(){dd.classList.add('ant-select-dropdown-hidden');input.setAttribute('aria-expanded','false');}
 sel.addEventListener('click',e=>{if(e.target.closest('.ant-select-dropdown'))return;open();});
 input.addEventListener('input',()=>{ const q=input.value.trim().toLowerCase();
   rows.forEach(r=>{ r.style.display=(!q||r.getAttribute('data-value').toLowerCase().includes(q))?'':'none'; }); });
 rows.forEach(r=>r.addEventListener('click',()=>{ const lbl=r.querySelector('span[aria-label]').textContent;
   if(![...wrap.querySelectorAll('.ant-select-selection-item')].some(t=>t.getAttribute('title')===lbl)){
     const t=document.createElement('span');t.className='ant-select-selection-item';t.setAttribute('title',lbl);
     const x=document.createElement('span');x.className='ant-select-selection-item-remove';x.textContent='x';
     x.addEventListener('click',e=>{e.stopPropagation();t.remove();}); t.append(lbl,x);wrap.insertBefore(t,wrap.firstChild);}
   close(); }));
 window.__tags=()=>[...wrap.querySelectorAll('.ant-select-selection-item')].map(t=>t.getAttribute('title'));
</script></body></html>
""".replace("__ROWS__", _ROWS))


async def _run(no_filter: bool):
    aw = pytest.importorskip("playwright.async_api")
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
            await page.set_content(_DOM)
            adapter = PlaywrightAdapter(page)
            plan = ActionPlan(action_type="select", input_value="Target-20240101-999",
                              options=ExecutionOptions(timeout_ms=4000, select_no_filter=no_filter))
            target = ResolvedTarget(ref='[data-testid="select-items"]', confidence=0.75,
                                    resolver_name="fuzzy_text", metadata={"role": "combobox"})
            try:
                res = await adapter.execute(plan, target)
                success = res.success
            except Exception:
                success = False
            tags = await page.evaluate("window.__tags()")
            return success, tags
        finally:
            await browser.close()


async def test_default_types_and_fails_on_guid_valued_dropdown():
    """Baseline: the default path types the label, the GUID filter empties the
    list, and nothing is selected — the exact failure this feature addresses."""
    success, tags = await _run(no_filter=False)
    assert success is False
    assert tags == []


async def test_select_no_filter_scans_and_selects():
    """select_no_filter skips typing, scans the list, and selects the option."""
    success, tags = await _run(no_filter=True)
    assert success is True
    assert tags == ["Target-20240101-999"]
