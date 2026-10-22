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
