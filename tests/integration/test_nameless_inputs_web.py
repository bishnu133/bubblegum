"""Regression: per-field text entry on a form whose inputs have NO accessible
name (Ant form labels use ``for=`` ids the inputs don't carry — broken
label/​input association), so grounding can only produce a nameless
``role=textbox`` that matches every input.

Two failure modes this covers:
  1. A nameless ``role=textbox`` must not be silently filled at ``.first`` — that
     piles every value into the first input on the page.
  2. The label-based DOM input resolver must target each field by its *visible*
     form-item label — including a phrase written without spaces
     (``FieldThree`` → "Field Three") — and must NOT fall back to
     the first input when nothing matches.

Runs against a real browser; skips when none is available. Set
``BG_CHROMIUM_EXECUTABLE`` to point at a Chromium binary if the default download
isn't present.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

# Three text inputs, each labelled via a <label for=...> whose id the input does
# NOT carry (only data-testid), so none of them has an accessible name.
_FORM = """
<form>
 <div class="ant-form-item"><div class="ant-form-item-label"><label for="name" title="Field One">Field One</label></div>
   <div class="ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
   <span class="ant-input-affix-wrapper"><input data-testid="input-one" class="ant-input" type="text" value=""></span></div></div></div></div>
 <div class="ant-form-item"><div class="ant-form-item-label"><label for="fieldTwo" title="Field Two">Field Two</label></div>
   <div class="ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
   <input data-testid="input-two" class="ant-input" type="text" value=""></div></div></div></div>
 <div class="ant-form-item"><div class="ant-form-item-label"><label for="src" title="Field Three">Field Three</label></div>
   <div class="ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
   <span class="ant-input-affix-wrapper"><input data-testid="input-three" class="ant-input" type="text" value=""></span></div></div></div></div>
</form>
"""


async def _adapter(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(_FORM)
    return browser, page, PlaywrightAdapter(page)


async def test_nameless_role_textbox_is_not_filled_at_first():
    """A `type` on a nameless role=textbox (multi-match) must not fill .first."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page, adapter = await _adapter(p)
        try:
            plan = ActionPlan(action_type="type", input_value="HELLO",
                              options=ExecutionOptions(timeout_ms=3000))
            target = ResolvedTarget(ref="role=textbox", confidence=0.7,
                                    resolver_name="llm_grounding", metadata={})
            res = await adapter.execute(plan, target)
            values = await page.evaluate(
                "[...document.querySelectorAll('input.ant-input')].map(i=>i.value)"
            )
            assert res.success is False
            assert values == ["", "", ""], "a nameless textbox was silently filled"
        finally:
            await browser.close()


async def test_find_input_targets_each_field_by_label():
    """find_input resolves each field by its visible label, incl. a spaceless phrase."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page, adapter = await _adapter(p)
        try:
            async def marks(phrase, testid):
                ref = await adapter.find_input(phrase)
                assert ref, f"no input resolved for {phrase!r}"
                # The resolver marks the winner with data-bg-input="1"; assert it
                # is the field we expect (not the first-input default).
                got = await page.eval_on_selector(
                    '[data-bg-input="1"]', "e => e.getAttribute('data-testid')"
                )
                assert got == testid, f"{phrase!r} resolved to {got}, expected {testid}"

            await marks("Field One", "input-one")
            await marks("Field Two", "input-two")
            # spaceless phrase must still match the spaced label
            await marks("FieldThree", "input-three")
            # a phrase that matches no label must NOT fall back to the first input
            assert await adapter.find_input("Nonexistent Widget Xyz") is None
        finally:
            await browser.close()
