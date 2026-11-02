"""Feature: select from a custom picker panel (checkable tags + Confirm).

Some selects render their popup as a custom panel instead of an option list —
an Ant ``Select`` with ``dropdownRender`` showing grouped checkable tags and
Cancel / Confirm buttons. There are no option rows, and nothing appears in the
field until Confirm, so the option-list path couldn't find the values (and kept
re-clicking, toggling a tag back off). A select step now ticks every requested
item in such a panel and clicks its Confirm button; ordinary option-list
selects (single and multi) behave as before.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a Chromium binary if needed.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]


def _tag(t: str) -> str:
    return (f'<div><span class="ant-tag ant-tag-checkable" style="margin:5px;border:1px solid #d9d9d9">'
            f'<span>{t}</span></span></div>')


def _group(title: str, tags: list[str]) -> str:
    return (f'<div style="display:flex;flex-direction:column;padding:10px 0">'
            f'<span aria-label="{title}" style="margin-left:5px">{title}</span>'
            f'<div style="display:flex;flex-flow:wrap">{"".join(_tag(t) for t in tags)}</div></div>')


_PANEL = (
    '<div class="ant-select-dropdown ant-select-dropdown-hidden ant-select-dropdown-empty" '
    'style="position:absolute;top:36px;left:0;width:420px;z-index:1050;background:#fff">'
    '<div><div style="display:flex;flex-direction:column;background:white">'
    '<div style="padding:16px;font-weight:bold">Select content tags</div>'
    '<div style="padding:0 10px">'
    + _group("Domain", ["MentalHealth", "Nutrition", "PhysicalActivity", "Screening"])
    + _group("Task Descriptor", ["AerobicIncrease", "SleepTrack", "StepsTrack", "SubstituteHealthier"])
    + _group("Theme", ["ThemeHealthy", "ThemeStress"])
    + '</div><div style="padding:15px;display:flex"><div style="margin-left:auto">'
    '<button data-testid="profileTagDropdownCancel" type="button" class="ant-btn ant-btn-default"><span>Cancel</span></button>'
    '<button data-testid="profileTagDropdownConfirm" type="button" class="ant-btn ant-btn-primary"><span>Confirm</span></button>'
    '</div></div></div></div></div>'
)

_PAGE = """<!doctype html><html><head><style>
.ant-select{position:relative;display:block;width:420px;min-height:30px;border:1px solid #d9d9d9}
.ant-select-dropdown-hidden{display:none}
.ant-tag-checkable-checked{background:#1677ff;color:#fff}
.ant-select-selection-item{margin-right:4px;background:#f0f0f0}
</style></head><body><form style="padding:20px">
<div class="ant-form-item"><div data-testid="action-content-tags" class="ant-row ant-form-item-row">
 <div class="ant-col ant-form-item-label"><label for="tags" title="Content Tags">Content Tags</label></div>
 <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
  <div id="tagsSel" class="ant-select ant-select-outlined ant-select-in-form-item ant-select-multiple ant-select-show-arrow ant-select-show-search"
       data-testid="action-content-tags-option">
   <div class="ant-select-selector"><span class="ant-select-selection-wrap"><div class="ant-select-selection-overflow">
    <div class="ant-select-selection-overflow-item ant-select-selection-overflow-item-suffix"><div class="ant-select-selection-search">
     <input id="content-tags-option" autocomplete="off" class="ant-select-selection-search-input" role="combobox" aria-expanded="false"
      aria-haspopup="listbox" aria-owns="content-tags-option_list" aria-controls="content-tags-option_list" type="search" value=""
      style="opacity:0" readonly unselectable="on"></div></div></div>
    <span class="ant-select-selection-placeholder">Select tags</span></span></div>
   <span class="ant-select-arrow" aria-hidden="true">v</span>
   __PANEL__
  </div></div></div>
  <div class="ant-form-item-additional"><div class="ant-form-item-extra">Keywords that describe the content</div></div>
 </div></div></div>

<div class="ant-form-item" style="margin-top:320px"><div class="ant-row ant-form-item-row">
 <div class="ant-col ant-form-item-label"><label for="colours" title="Colours">Colours</label></div>
 <div class="ant-col ant-form-item-control">
  <div id="colSel" class="ant-select ant-select-multiple ant-select-show-search">
   <div class="ant-select-selector"><span class="ant-select-selection-wrap"><div class="ant-select-selection-overflow">
    <div class="ant-select-selection-search"><input id="colours" class="ant-select-selection-search-input" role="combobox"
     aria-expanded="false" aria-owns="colours_list" aria-controls="colours_list" type="search" value=""></div></div>
    <span class="ant-select-selection-placeholder">Select colours</span></span></div></div>
 </div></div></div>
<div style="display:flex;justify-content:flex-end;margin-top:40px">
 <button type="button" class="ant-btn" data-log="FORM:Cancel"><span>Cancel</span></button>
 <button type="button" class="ant-btn ant-btn-primary" data-log="FORM:Create"><span>Create</span></button></div>
</form>
<div><div id="colDd" class="ant-select-dropdown ant-select-dropdown-hidden" style="position:absolute;z-index:1050;background:#fff;top:420px;left:20px;width:300px">
 <div role="listbox" id="colours_list" style="height:0;width:0;overflow:hidden"></div>
 <div class="rc-virtual-list"><div class="rc-virtual-list-holder-inner">
  <div class="ant-select-item ant-select-item-option" title="Red"><div class="ant-select-item-option-content">Red</div></div>
  <div class="ant-select-item ant-select-item-option" title="Green"><div class="ant-select-item-option-content">Green</div></div>
  <div class="ant-select-item ant-select-item-option" title="Blue"><div class="ant-select-item-option-content">Blue</div></div>
 </div></div></div></div>
<script>
window.__log = [];
document.querySelectorAll('[data-log]').forEach(b => b.addEventListener('click', () => __log.push(b.dataset.log)));
const addItem = (sel, t) => {
  const wrap = sel.querySelector('.ant-select-selection-overflow');
  const s = document.createElement('span'); s.className = 'ant-select-selection-item'; s.title = t; s.textContent = t;
  wrap.insertBefore(s, wrap.lastElementChild);
  sel.querySelector('.ant-select-selection-placeholder').style.display = 'none';
};
// Content Tags: custom panel inside the select; tags toggle; only Confirm commits.
const tSel = document.getElementById('tagsSel'), dd = tSel.querySelector('.ant-select-dropdown');
let committed = (window.__preset || []).slice();
const syncChecks = () => dd.querySelectorAll('.ant-tag-checkable').forEach(t =>
  t.classList.toggle('ant-tag-checkable-checked', committed.includes(t.textContent.trim())));
const render = () => { tSel.querySelectorAll('.ant-select-selection-item').forEach(n => n.remove()); committed.forEach(t => addItem(tSel, t)); };
tSel.addEventListener('click', e => {
  if (e.target.closest('.ant-select-dropdown')) return;
  if (dd.classList.contains('ant-select-dropdown-hidden')) { syncChecks(); dd.classList.remove('ant-select-dropdown-hidden'); }
});
dd.querySelectorAll('.ant-tag-checkable').forEach(t => t.addEventListener('click', () => t.classList.toggle('ant-tag-checkable-checked')));
dd.querySelector('[data-testid=profileTagDropdownConfirm]').addEventListener('click', () => {
  committed = Array.from(dd.querySelectorAll('.ant-tag-checkable-checked')).map(t => t.textContent.trim());
  render(); dd.classList.add('ant-select-dropdown-hidden'); __log.push('PANEL:Confirm');
});
dd.querySelector('[data-testid=profileTagDropdownCancel]').addEventListener('click', () => {
  dd.classList.add('ant-select-dropdown-hidden'); __log.push('PANEL:Cancel');
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') dd.classList.add('ant-select-dropdown-hidden'); });
render();
// Colours: ordinary Ant multi-select with option rows (portalled).
const cSel = document.getElementById('colSel'), cDd = document.getElementById('colDd');
cSel.addEventListener('click', () => cDd.classList.remove('ant-select-dropdown-hidden'));
cDd.querySelectorAll('.ant-select-item-option').forEach(o => o.addEventListener('click', () => addItem(cSel, o.title)));
window.__sel = (id) => Array.from(document.querySelectorAll('#' + id + ' .ant-select-selection-item')).map(n => n.title);
window.__open = () => !dd.classList.contains('ant-select-dropdown-hidden');
</script></body></html>""".replace("__PANEL__", _PANEL)


# A page closer to a real app: the panel opens on mousedown and covers its own
# field, picked tags change only their inline colours (no "-checked" class), and
# an "Eligibility Tags" multi-select sits nearby.
_REAL_TAGS = {
    "Domain": ["MentalHealth", "Nutrition", "PhysicalActivity", "Screening"],
    "Task Descriptor": ["AerobicIncrease", "SleepTrack", "StepsStart", "StepsTrack",
                        "SubstituteDrink", "SubstituteFood", "SubstituteHealthier"],
    "Theme": ["ThemeHealthy", "ThemeIndependence", "ThemeStress"],
}
_OFF = "margin: 5px; color: rgba(0, 0, 0, 0.65); background-color: rgb(250, 250, 250); border: 1px solid rgb(217, 217, 217);"
_ON = "margin: 5px; color: rgb(255, 255, 255); background-color: rgb(24, 144, 255); border: 1px solid rgb(24, 144, 255);"


def _real_page(style_only: bool, preset=None) -> str:
    groups = "".join(
        f'<div style="display:flex;flex-direction:column;padding-top:10px;padding-bottom:10px">'
        f'<span aria-label="{g}" style="margin-left:5px">{g}</span><div style="display:flex;flex-flow:wrap">'
        + "".join(f'<div><span class="ant-tag ant-tag-checkable" style="{_OFF}"><span>{t}</span></span></div>' for t in ts)
        + "</div></div>"
        for g, ts in _REAL_TAGS.items()
    )
    preset = list(preset or [])
    return f"""<!doctype html><html><head><style>
body{{margin:0;font-family:Helvetica}}
.ant-select{{position:relative;display:block;min-height:32px;border:1px solid #d9d9d9;cursor:pointer}}
.ant-select-selector{{min-height:30px;padding:0 8px}}
.ant-select-dropdown{{position:absolute;z-index:1050;background:#fff;box-shadow:0 2px 8px #0003}}
.ant-select-dropdown-hidden{{display:none}}
.ant-tag{{display:inline-block;padding:0 7px;cursor:pointer}}
.ant-select-selection-item{{margin-right:4px;background:#f0f0f0}}
.ant-btn{{padding:4px 15px}}
</style></head><body>
<form class="ant-form ant-form-vertical" style="width:440px;margin:58px auto">
<h4>Action Details</h4>
<div class="ant-form-item"><div class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-label"><label for="title" title="Action Title">Action Title</label></div>
 <div class="ant-col ant-form-item-control"><input class="ant-input" type="text" value=""></div></div></div>
<div class="ant-form-item"><div class="ant-row"><div class="ant-col ant-form-item-label"><label class="ant-form-item-required" title="Action Period">Action Period</label></div>
 <div style="height:40px"></div></div></div>
<div class="ant-form-item ant-form-item-vertical"><div data-testid="action-content-tags" class="ant-row ant-form-item-row">
 <div class="ant-col ant-form-item-label"><label for="tags" title="Content Tags">Content Tags</label></div>
 <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
  <div id="tagsSel" class="ant-select ant-select-outlined ant-select-in-form-item ant-select-multiple ant-select-show-arrow ant-select-show-search" data-testid="action-content-tags-option" aria-describedby="tags_extra" style="width:100%">
   <div class="ant-select-selector"><span class="ant-select-selection-wrap"><div class="ant-select-selection-overflow">
    <div class="ant-select-selection-overflow-item ant-select-selection-overflow-item-suffix" style="opacity:1"><div class="ant-select-selection-search" style="width:4px">
     <input id="content-tags-option" autocomplete="off" class="ant-select-selection-search-input" role="combobox" aria-expanded="false" aria-haspopup="listbox"
      aria-owns="content-tags-option_list" aria-autocomplete="list" aria-controls="content-tags-option_list" aria-describedby="tags_extra" type="search" value=""
      style="opacity:0" readonly unselectable="on"><span class="ant-select-selection-search-mirror" aria-hidden="true">&nbsp;</span></div></div></div>
    <span class="ant-select-selection-placeholder">Select tags</span></span></div>
   <span class="ant-select-arrow" unselectable="on" aria-hidden="true" style="user-select:none"><span role="img" aria-label="down" class="anticon anticon-down ant-select-suffix">v</span></span>
   <div class="ant-select-dropdown ant-select-dropdown-hidden ant-select-dropdown-empty ant-select-dropdown-placement-topLeft" style="inset:auto auto -120px 0px;box-sizing:border-box;width:441px">
    <div><div style="color:black;display:flex;flex-direction:column;padding:0;cursor:default;background:white">
     <div style="padding:16px;font-weight:bold;font-size:18px;border-bottom:1px solid rgb(217,217,217)">Select content tags</div>
     <div style="border-bottom:1px solid rgb(217,217,217);padding-left:10px;padding-right:10px">{groups}</div>
     <div style="padding:15px;display:flex;align-items:flex-end"><div style="margin-left:auto">
      <button data-testid="profileTagDropdownCancel" type="button" class="ant-btn ant-btn-default" style="margin-right:10px"><span>Cancel</span></button>
      <button data-testid="profileTagDropdownConfirm" type="button" class="ant-btn ant-btn-primary"><span>Confirm</span></button>
     </div></div></div></div></div>
  </div></div></div>
  <div class="ant-form-item-additional"><div id="tags_extra" class="ant-form-item-extra"><div>Keywords that describe the content including but not limited to domains and recommendations</div></div></div>
 </div></div></div>
<div style="padding-bottom:8px">Eligibility Criteria</div>
<div class="ant-card"><div class="ant-card-head"><b>Eligibility Criteria #1</b></div><div class="ant-card-body">
 <span>Eligibility Tags</span>
 <div style="margin-top:10px;display:flex">
  <div class="ant-select ant-select-single ant-select-disabled" data-testid="undefined-1-profile-tag-subtype-1" style="width:100px"><div class="ant-select-selector">
   <input disabled class="ant-select-selection-search-input" role="combobox" aria-expanded="false" aria-owns="rc_select_4_list" aria-controls="rc_select_4_list" readonly type="search" id="rc_select_4" style="opacity:0">
   <span class="ant-select-selection-item" title="All">All</span></div></div>
  <div id="eligSel" class="ant-select ant-select-multiple ant-select-show-search" data-testid="undefined-1-profile-tag-value-1" style="min-width:70%;flex-grow:1"><div class="ant-select-selector"><span class="ant-select-selection-wrap"><div class="ant-select-selection-overflow">
   <div class="ant-select-selection-search"><input class="ant-select-selection-search-input" role="combobox" aria-expanded="false" aria-owns="rc_select_5_list" aria-controls="rc_select_5_list" readonly type="search" id="rc_select_5" style="opacity:0"></div></div>
   <span class="ant-select-selection-placeholder"></span></span></div></div>
 </div>
</div></div>
<div class="ant-form-item"><div data-testid="action-type-test-id" class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-label"><label for="type" class="ant-form-item-required" title="Action Type">Action Type</label></div>
 <div class="ant-col ant-form-item-control"><div class="ant-select ant-select-single ant-select-show-search" data-testid="action-type-select"><div class="ant-select-selector">
  <input id="type" class="ant-select-selection-search-input" role="combobox" aria-expanded="false" aria-owns="type_list" aria-controls="type_list" type="search" value="">
  <span class="ant-select-selection-placeholder">Select type</span></div></div></div></div></div>
<div style="display:flex;justify-content:flex-end;margin-top:40px"><button type="button" class="ant-btn" data-log="FORM:Cancel"><span>Cancel</span></button><button type="button" class="ant-btn ant-btn-primary" data-log="FORM:Create"><span>Create</span></button></div>
</form>
<div><div id="eligDd" class="ant-select-dropdown ant-select-dropdown-hidden ant-select-dropdown-empty" style="position:absolute;z-index:1050;width:300px"><div><div class="ant-select-empty">No data</div></div></div></div>
<script>
window.__log=[];
document.querySelectorAll('[data-log]').forEach(b=>b.addEventListener('click',()=>__log.push(b.dataset.log)));
const STYLE_ONLY={str(style_only).lower()};
const OFF={_OFF!r}, ON={_ON!r};
const tSel=document.getElementById('tagsSel'), dd=tSel.querySelector('.ant-select-dropdown'), inp=document.getElementById('content-tags-option');
let committed={preset!r}; const draft=new Set();
const paint=()=>dd.querySelectorAll('.ant-tag-checkable').forEach(t=>{{const on=draft.has(t.textContent.trim());
  t.setAttribute('style',on?ON:OFF); if(!STYLE_ONLY) t.classList.toggle('ant-tag-checkable-checked',on);}});
const open=()=>{{if(!dd.classList.contains('ant-select-dropdown-hidden'))return; draft.clear(); committed.forEach(c=>draft.add(c)); paint();
  dd.classList.remove('ant-select-dropdown-hidden'); tSel.classList.add('ant-select-open','ant-select-focused'); inp.setAttribute('aria-expanded','true');}};
const close=()=>{{dd.classList.add('ant-select-dropdown-hidden'); tSel.classList.remove('ant-select-open'); inp.setAttribute('aria-expanded','false');}};
// rc-select opens on mousedown on the selector; clicks inside the popup keep it open
tSel.querySelector('.ant-select-selector').addEventListener('mousedown',e=>{{e.preventDefault();open();}});
tSel.querySelector('.ant-select-arrow').addEventListener('mousedown',e=>{{e.preventDefault();open();}});
dd.addEventListener('mousedown',e=>e.preventDefault());
dd.querySelectorAll('.ant-tag-checkable').forEach(t=>t.addEventListener('click',()=>{{const k=t.textContent.trim(); draft.has(k)?draft.delete(k):draft.add(k); paint();}}));
const render=()=>{{tSel.querySelectorAll('.ant-select-selection-item').forEach(n=>n.remove());
  const wrap=tSel.querySelector('.ant-select-selection-overflow');
  committed.forEach(k=>{{const d=document.createElement('div');d.className='ant-select-selection-overflow-item';
    d.innerHTML='<span class="ant-select-selection-item" title="'+k+'"><span class="ant-select-selection-item-content">'+k+'</span></span>';
    wrap.insertBefore(d,wrap.lastElementChild);}});
  tSel.querySelector('.ant-select-selection-placeholder').style.display=committed.length?'none':'';}};
dd.querySelector('[data-testid=profileTagDropdownConfirm]').addEventListener('click',()=>{{committed=[...draft]; render(); close(); __log.push('PANEL:Confirm');}});
dd.querySelector('[data-testid=profileTagDropdownCancel]').addEventListener('click',()=>{{close(); __log.push('PANEL:Cancel');}});
document.addEventListener('mousedown',e=>{{if(!tSel.contains(e.target))close();}});
document.addEventListener('keydown',e=>{{if(e.key==='Escape')close();}});
// Eligibility Tags: an ordinary multi-select with no options
const eSel=document.getElementById('eligSel'), eDd=document.getElementById('eligDd');
eSel.addEventListener('mousedown',e=>{{const r=eSel.getBoundingClientRect(); eDd.style.top=(r.bottom+window.scrollY)+'px'; eDd.style.left=r.left+'px'; eDd.classList.remove('ant-select-dropdown-hidden');}});
render(); window.__sel=()=>committed.slice(); window.__open=()=>!dd.classList.contains('ant-select-dropdown-hidden');
</script></body></html>"""


async def _run_real(steps, *, style_only=True, preset=None):
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
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.set_content(_real_page(style_only, preset))
            results = [await act(s, channel="web", page=page) for s in steps]
            return results, {
                "tags": await page.evaluate("__sel()"),
                "open": await page.evaluate("__open()"),
                "log": await page.evaluate("__log"),
            }
        finally:
            await browser.close()


async def _run(steps, preset=None):
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
            html = _PAGE if preset is None else _PAGE.replace(
                "<script>", f"<script>window.__preset={preset!r};", 1)
            await page.set_content(html)
            results = [await act(s, channel="web", page=page) for s in steps]
            return results, {
                "tags": await page.evaluate("__sel('tagsSel')"),
                "colours": await page.evaluate("__sel('colSel')"),
                "open": await page.evaluate("__open()"),
                "log": await page.evaluate("__log"),
            }
        finally:
            await browser.close()


@pytest.mark.parametrize(
    "step",
    [
        'Select "MentalHealth, SleepTrack" from Content Tags',
        "Select MentalHealth, SleepTrack in Content Tags",
        'Select "MentalHealth,SleepTrack" from the Content Tags field',
    ],
)
async def test_multiple_tags_ticked_and_confirmed(step):
    (res,), state = await _run([step])
    assert res.status == "passed", res.error
    assert state["tags"] == ["MentalHealth", "SleepTrack"]
    assert state["open"] is False
    assert state["log"] == ["PANEL:Confirm"]


async def test_single_tag():
    (res,), state = await _run(['Select "Nutrition" from Content Tags'])
    assert res.status == "passed", res.error
    assert state["tags"] == ["Nutrition"]


async def test_already_selected_tag_is_not_toggled_off():
    (res,), state = await _run(['Select "MentalHealth, Screening" from Content Tags'], preset=["MentalHealth"])
    assert res.status == "passed", res.error
    assert sorted(state["tags"]) == ["MentalHealth", "Screening"]


async def test_unknown_tag_fails_and_commits_nothing():
    (res,), state = await _run(['Select "MentalHealth, NoSuchTag" from Content Tags'])
    assert res.status == "failed"
    assert "NoSuchTag" in str(res.error)
    assert state["tags"] == []
    assert "PANEL:Confirm" not in state["log"]


async def test_two_steps_in_a_row():
    results, state = await _run([
        'Select "MentalHealth" from Content Tags',
        'Select "ThemeStress" from Content Tags',
    ])
    assert all(r.status == "passed" for r in results), [r.error for r in results]
    assert state["tags"] == ["MentalHealth", "ThemeStress"]


async def test_ordinary_multi_select_unchanged():
    (res,), state = await _run(['Select "Red, Blue" from Colours'])
    assert res.status == "passed", res.error
    assert state["colours"] == ["Red", "Blue"]
    assert state["tags"] == []


@pytest.mark.parametrize("style_only", [True, False], ids=["picked-by-inline-style", "picked-by-class"])
async def test_real_page_multiple_tags(style_only):
    (res,), state = await _run_real(['Select "MentalHealth, SleepTrack, ThemeStress" from Content Tags'],
                                    style_only=style_only)
    assert res.status == "passed", res.error
    assert state["tags"] == ["MentalHealth", "SleepTrack", "ThemeStress"]
    assert state["open"] is False
    assert state["log"] == ["PANEL:Confirm"]


async def test_real_page_keeps_already_picked_style_only_tag():
    (res,), state = await _run_real(['Select "MentalHealth, Screening" from Content Tags'],
                                    preset=["MentalHealth"])
    assert res.status == "passed", res.error
    assert sorted(state["tags"]) == ["MentalHealth", "Screening"]


async def test_real_page_two_steps_style_only():
    results, state = await _run_real([
        'Select "Nutrition" from Content Tags',
        'Select "SubstituteFood, ThemeHealthy" from Content Tags',
    ])
    assert all(r.status == "passed" for r in results), [r.error for r in results]
    assert state["tags"] == ["Nutrition", "SubstituteFood", "ThemeHealthy"]


async def test_real_page_unknown_tag_names_it_and_applies_nothing():
    (res,), state = await _run_real(['Select "MentalHealth, NoSuchTag" from Content Tags'])
    assert res.status == "failed"
    assert "NoSuchTag" in str(res.error) and "not found" in str(res.error)
    assert state["tags"] == []
    assert state["log"] == ["PANEL:Cancel"]
