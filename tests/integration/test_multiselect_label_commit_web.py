"""Regression: commit-verification must run even when an Ant ``.ant-select`` is
grounded to its ``<label>`` (which sits OUTSIDE the widget).

The bug: ``_is_ant_select`` only recognised a select when the *resolved trigger
element* was itself inside ``.ant-select``. Grounding frequently resolves a
field by its label text, landing on the ``<label for=…>`` — outside the widget —
so the "did the click actually add a selection tag?" verification
(``_value_committed``) was skipped and a click that never committed was reported
as a **successful** select. Symptom in the wild: a multi-select step whose log
says ``passed`` while nothing is selected.

The fix climbs from the trigger to the associated ``.ant-select`` (self /
ancestor / descendant / the ``label[for]`` it is or sits inside), so:
  * a click that DOES add a tag is verified and passes, and
  * a click that does NOT commit is correctly reported as a failure (not a pass),
regardless of whether grounding resolved the widget or its label.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a specific Chromium binary if the default
Playwright download isn't present.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


def _dom(commit: bool) -> str:
    """An Ant multi-select 'Related domains' with a single option 'Rewards'.

    ``commit=True`` mimics normal Ant behaviour (clicking the option row adds a
    ``.ant-select-selection-item`` tag). ``commit=False`` mimics a widget that
    swallows the click without committing — the exact "passed but not selected"
    condition we must catch.
    """
    commit_js = (
        "const t=document.createElement('span');t.className='ant-select-selection-item';"
        "t.setAttribute('title','Rewards');t.textContent='Rewards';"
        "wrap.insertBefore(t,wrap.firstChild);"
        if commit else "/* no commit */"
    )
    return (
        "<!doctype html><html><body>"
        "<label id='lbl' for='domains' title='Related domains'>Related domains</label>"
        "<div class='ant-select ant-select-multiple ant-select-show-search'"
        " data-testid='input-relatedDomain'>"
        "  <div class='ant-select-selector'><span class='ant-select-selection-wrap'>"
        "    <div class='ant-select-selection-overflow'><div class='ant-select-selection-search'>"
        "      <input id='domains' class='ant-select-selection-search-input' role='combobox'"
        "       aria-expanded='false' aria-owns='domains_list' aria-controls='domains_list'"
        "       type='search' value='' readonly></div></div>"
        "    <span class='ant-select-selection-placeholder'></span></span></div>"
        "  <span class='ant-select-arrow'><span aria-label='down'>v</span></span>"
        "</div>"
        "<div><div class='ant-select-dropdown ant-select-dropdown-hidden' id='dd'><div>"
        "  <div role='listbox' id='domains_list' style='height:0;width:0;overflow:hidden'>"
        "    <div role='option' id='domains_list_0' aria-selected='false'>rewards</div></div>"
        "  <div class='rc-virtual-list'><div class='rc-virtual-list-holder-inner'>"
        "    <div name='domain' aria-selected='false' class='ant-select-item ant-select-item-option' id='opt'>"
        "      <div class='ant-select-item-option-content'><span aria-label='option-rewards'>Rewards</span></div>"
        "    </div></div></div>"
        "</div></div></div>"
        "<script>"
        " const sel=document.querySelector('.ant-select'),dd=document.getElementById('dd'),"
        "  input=document.getElementById('domains'),wrap=sel.querySelector('.ant-select-selection-wrap');"
        " function open(){dd.classList.remove('ant-select-dropdown-hidden');input.setAttribute('aria-expanded','true');}"
        " function close(){dd.classList.add('ant-select-dropdown-hidden');}"
        " sel.addEventListener('click',e=>{if(e.target.closest('.ant-select-dropdown'))return;open();});"
        " document.getElementById('lbl').addEventListener('click',open);"
        " document.getElementById('opt').addEventListener('click',()=>{" + commit_js + " close();});"
        " window.__n=()=>document.querySelectorAll('.ant-select-selection-item').length;"
        "</script></body></html>"
    )


async def _select(commit: bool, ref: str):
    """Run a ``select`` of 'Rewards' and return ``(success, tag_count)``."""
    aw = pytest.importorskip("playwright.async_api")
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover - environment without a browser
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_dom(commit))
            adapter = PlaywrightAdapter(page)
            plan = ActionPlan(
                action_type="select",
                input_value="Rewards",
                options=ExecutionOptions(timeout_ms=4000),
            )
            target = ResolvedTarget(ref=ref, confidence=0.9, resolver_name="test",
                                    metadata={"role": "combobox"})
            try:
                res = await adapter.execute(plan, target)
                success = res.success
            except Exception:
                success = False
            tags = await page.evaluate("window.__n()")
            return success, tags
        finally:
            await browser.close()


# The two refs represent the two ways grounding lands on this field: on the
# widget wrapper (data-testid) or on its <label> (accessible-name match).
_LABEL_REF = 'label[for="domains"]'
_WIDGET_REF = '[data-testid="input-relatedDomain"]'


async def test_label_resolved_noncommit_is_not_reported_as_selected():
    """The bug: label-resolved select whose click doesn't commit must FAIL."""
    success, tags = await _select(commit=False, ref=_LABEL_REF)
    assert tags == 0
    assert success is False, "non-committing select reported as passed (regression)"


async def test_label_resolved_commit_still_passes():
    """Guard: a genuine commit via the label path still passes and is verified."""
    success, tags = await _select(commit=True, ref=_LABEL_REF)
    assert tags == 1
    assert success is True


async def test_widget_resolved_noncommit_still_fails():
    """Guard: the in-widget path keeps catching a non-committing click."""
    success, tags = await _select(commit=False, ref=_WIDGET_REF)
    assert tags == 0
    assert success is False


# --- probe_others cleanup must not remove the committed selection -------------
# Regression: grounding resolves the field to its inner role=combobox <input>,
# while _other_select_triggers returns that input's OWN .ant-select container as
# a separate "other" candidate. The value is committed on the input, then the
# post-commit cleanup treats the same widget's selection as a stray and clicks
# its × to remove it — the step reports success while nothing stays selected.
# A real Ant tag has a functioning × (unlike the simpler DOM above), so this
# fixture wires one up.
_REMOVE_TAG_DOM = (
    "<!doctype html><html><body>"
    "<label for='domains' title='Related domains'>Related domains</label>"
    "<div class='ant-select ant-select-multiple ant-select-show-search' data-testid='input-relatedDomain'>"
    "  <div class='ant-select-selector'><span class='ant-select-selection-wrap' id='wrapR'>"
    "    <div class='ant-select-selection-overflow'><div class='ant-select-selection-search'>"
    "      <input id='domains' class='ant-select-selection-search-input' role='combobox'"
    "       aria-label='* Related domains' aria-expanded='false' aria-owns='domains_list'"
    "       aria-controls='domains_list' type='search' value='' readonly></div></div>"
    "    <span class='ant-select-selection-placeholder'></span></span></div>"
    "  <span class='ant-select-arrow'><span aria-label='down'>v</span></span></div>"
    "<div><div class='ant-select-dropdown ant-select-dropdown-hidden' id='dd'><div>"
    "  <div role='listbox' id='domains_list' style='height:0;width:0;overflow:hidden'>"
    "    <div role='option' id='domains_list_0' aria-selected='false'>rewards</div></div>"
    "  <div class='rc-virtual-list'><div class='rc-virtual-list-holder-inner'>"
    "    <div name='domain' aria-selected='false' class='ant-select-item ant-select-item-option' id='opt'>"
    "      <div class='ant-select-item-option-content'><span aria-label='option-rewards'>Rewards</span></div>"
    "    </div></div></div>"
    "</div></div></div>"
    "<script>"
    " const selR=document.querySelector('[data-testid=input-relatedDomain]');"
    " const dd=document.getElementById('dd'),input=document.getElementById('domains'),wrap=document.getElementById('wrapR');"
    " function open(){dd.classList.remove('ant-select-dropdown-hidden');input.setAttribute('aria-expanded','true');}"
    " function close(){dd.classList.add('ant-select-dropdown-hidden');input.setAttribute('aria-expanded','false');}"
    " selR.addEventListener('click',e=>{if(e.target.closest('.ant-select-dropdown'))return;open();});"
    " document.getElementById('opt').addEventListener('click',()=>{"
    "   if(!selR.querySelector('.ant-select-selection-item')){"
    "     const t=document.createElement('span');t.className='ant-select-selection-item';t.setAttribute('title','Rewards');"
    "     const x=document.createElement('span');x.className='ant-select-selection-item-remove';x.setAttribute('aria-label','close');x.textContent='x';"
    "     x.addEventListener('click',(e)=>{e.stopPropagation();t.remove();});"  # real Ant: × removes the tag
    "     t.append('Rewards',x);wrap.insertBefore(t,wrap.firstChild);}"
    "   close();});"
    " window.__n=()=>selR.querySelectorAll('.ant-select-selection-item').length;"
    "</script></body></html>"
)


async def test_committed_selection_survives_probe_others_cleanup():
    """A committed selection must not be removed by the same-widget cleanup."""
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
            await page.set_content(_REMOVE_TAG_DOM)
            adapter = PlaywrightAdapter(page)
            plan = ActionPlan(action_type="select", input_value="Rewards",
                              options=ExecutionOptions(timeout_ms=4000))
            target = ResolvedTarget(ref='role=combobox[name="* Related domains"]',
                                    confidence=0.75, resolver_name="fuzzy_text",
                                    metadata={"role": "combobox"})
            res = await adapter.execute(plan, target)
            tags = await page.evaluate("window.__n()")
            assert res.success is True
            assert tags == 1, "committed selection was removed by same-widget cleanup (regression)"
        finally:
            await browser.close()
