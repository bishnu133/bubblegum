"""Checkbox DOM resolution + quoted-segment fallbacks for radio/dropdown steps.

The deterministic parser drops or mangles the target for two common phrasings:
  * `Select "NA" radio button for Recommendation Sex` -> target=None (the "for …"
    tail defeats extraction), so the radio/checkbox resolvers must fall back to
    the quoted option label.
  * `Select "Aerobic" from "Recommendation Tags" drop down` -> target mangled to
    `Recommendation Tags" drop down`, so the dropdown resolver must use the 2nd
    quoted segment (the dropdown's own name), else it mis-scores and lands on the
    first select on the page.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


def _intent(instruction, action="select", target_phrase=None, value=None):
    return StepIntent(instruction=instruction, channel="web", action_type=action,
                      target_phrase=target_phrase, input_value=value, context={})


# --- _clean_dropdown_phrase (pure) -----------------------------------------

@pytest.mark.parametrize("raw,clean", [
    ('Recommendation Tags" drop down', "Recommendation Tags"),
    ('Division Name" dropdown', "Division Name"),
    ('"Eligibility Tags" select', "Eligibility Tags"),
    ('Challenges Joined list', "Challenges Joined"),
    ("Amount (SGD)", "Amount (SGD)"),
])
def test_clean_dropdown_phrase(raw, clean):
    assert sdk._clean_dropdown_phrase(raw) == clean


# --- radio / checkbox quoted-label fallback --------------------------------

class _RadioAdapter:
    def __init__(self):
        self.calls = []

    async def find_radio(self, phrase):
        self.calls.append(phrase)
        return {"selector": '[data-bg-radio="1"]', "checked": False, "name": phrase}


class _CheckboxAdapter:
    def __init__(self):
        self.calls = []

    async def find_checkbox(self, phrase):
        self.calls.append(phrase)
        return {"selector": '[data-bg-checkbox="1"]', "checked": False, "name": phrase}


def test_radio_falls_back_to_quoted_option_when_target_missing():
    a = _RadioAdapter()
    intent = _intent('Select "NA" radio button for Recommendation Sex', target_phrase=None)
    t = _run(sdk._maybe_resolve_radio(a, "web", intent))
    assert t is not None and t.resolver_name == "radio_dom"
    assert a.calls == ["NA"]           # used the quoted option, not None
    assert intent.action_type == "click"


def test_checkbox_falls_back_to_quoted_and_sets_check():
    a = _CheckboxAdapter()
    intent = _intent('Select "Food purchase" checkbox', target_phrase=None)
    t = _run(sdk._maybe_resolve_checkbox(a, "web", intent))
    assert t is not None and t.resolver_name == "checkbox_dom"
    assert a.calls == ["Food purchase"]
    assert intent.action_type == "check"


def test_checkbox_uncheck_intent_sets_uncheck():
    a = _CheckboxAdapter()
    intent = _intent('Uncheck "Drink purchase" checkbox', target_phrase="Drink purchase")
    t = _run(sdk._maybe_resolve_checkbox(a, "web", intent))
    assert t is not None
    assert intent.action_type == "uncheck"


def test_checkbox_resolver_skips_non_checkbox_steps():
    a = _CheckboxAdapter()
    intent = _intent('Select "NA" radio button for Sex', target_phrase="NA")
    assert _run(sdk._maybe_resolve_checkbox(a, "web", intent)) is None
    assert a.calls == []


# --- select-trigger uses the dropdown's own (2nd quoted) name --------------

class _SelectAdapter:
    def __init__(self):
        self.calls = []

    async def find_select_trigger(self, phrase, value):
        self.calls.append((phrase, value))
        return '[data-bg-select="1"]'


def test_select_trigger_uses_second_quoted_segment_as_name():
    a = _SelectAdapter()
    intent = _intent('Select "Aerobic" from "Recommendation Tags" drop down',
                     action="select", target_phrase='Recommendation Tags" drop down', value="Aerobic")
    t = _run(sdk._maybe_resolve_select_trigger(a, "web", intent))
    assert t is not None and t.resolver_name == "select_trigger_dom"
    # Clean dropdown name + value — not the mangled parsed target.
    assert a.calls == [("Recommendation Tags", "Aerobic")]


# --- browser: end-to-end checkbox toggling (Ant hidden-input pattern) -------

_METRICS = """
<div class="ant-checkbox-group" id="metrics">
  <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked"><span class="ant-checkbox ant-checkbox-checked"><input class="ant-checkbox-input" type="checkbox" value="food" checked=""><span class="ant-checkbox-inner"></span></span><span class="ant-checkbox-label">Food purchase</span></label>
  <label class="ant-checkbox-wrapper ant-checkbox-wrapper-checked"><span class="ant-checkbox ant-checkbox-checked"><input class="ant-checkbox-input" type="checkbox" value="drink" checked=""><span class="ant-checkbox-inner"></span></span><span class="ant-checkbox-label">Drink purchase</span></label>
  <label class="ant-checkbox-wrapper"><span class="ant-checkbox"><input class="ant-checkbox-input" type="checkbox" value="grocery"><span class="ant-checkbox-inner"></span></span><span class="ant-checkbox-label">Grocery purchase</span></label>
</div>
"""


@pytest.mark.playwright
def test_checkbox_dom_selects_and_toggles_idempotently() -> None:
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
                await page.set_content(_METRICS)

                async def checked(v):
                    return await page.locator(f'input[value="{v}"]').is_checked()

                r1 = await sdk.act('Select "Food purchase" checkbox', channel="web", page=page)
                r2 = await sdk.act('Select "Grocery purchase" checkbox', channel="web", page=page)
                r3 = await sdk.act('Uncheck "Drink purchase" checkbox', channel="web", page=page)
                return (
                    r1.status, await checked("food"),     # already on -> stays on
                    r2.status, await checked("grocery"),   # off -> on
                    r3.status, await checked("drink"),     # on -> off
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    s1, food, s2, grocery, s3, drink = asyncio.run(go())
    assert (s1, s2, s3) == ("passed", "passed", "passed")
    assert food is True and grocery is True and drink is False
