"""Section-disambiguated text inputs.

Two sections ("Eligibility"/"Recommendation") often carry an identically labelled
field ("Minimum Age"). The a11y snapshot can resolve such a field as "unique" and
pick the wrong section, dropping the value in the other section. A pre-resolver
claims the step ahead of grounding — but ONLY when the field's visible label
collides with another field and a section heading named in the phrase is what
disambiguates it (``sectioned``). A normal, unique field is left to grounding.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


def _intent(instruction, target_phrase, action="type"):
    return StepIntent(instruction=instruction, channel="web", action_type=action,
                      target_phrase=target_phrase, input_value="20", context={})


class _InputAdapter:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def find_input_ex(self, phrase):
        self.calls.append(phrase)
        return self._result


def test_pre_resolver_claims_only_when_sectioned():
    a = _InputAdapter({"selector": '[data-bg-input="1"]', "sectioned": True,
                       "section": "recommendation criteria #1", "score": 2.5})
    t = _run(sdk._maybe_resolve_sectioned_input(a, "web", _intent(
        'Enter "20" into Recommendation Minimum Age', "Recommendation Minimum Age")))
    assert t is not None and t.resolver_name == "input_dom"
    assert t.metadata.get("sectioned") is True


def test_pre_resolver_defers_when_not_sectioned():
    # Unique field: no visible-label collision -> sectioned False -> let grounding run.
    a = _InputAdapter({"selector": '[data-bg-input="1"]', "sectioned": False,
                       "section": "", "score": 3.0})
    t = _run(sdk._maybe_resolve_sectioned_input(a, "web", _intent(
        'Enter "Demo" into Challenge Tagline', "Challenge Tagline")))
    assert t is None


def test_pre_resolver_ignores_non_type_steps():
    a = _InputAdapter({"selector": "x", "sectioned": True})
    t = _run(sdk._maybe_resolve_sectioned_input(a, "web", _intent(
        'Click Save', "Save", action="click")))
    assert t is None and a.calls == []


# --- browser: two sections, colliding "Minimum/Maximum Age" + Male/Female -----

_TWO_SECTION_FORM = """
<form class="ant-form">
<div style="margin-top:40px"><h4>Eligibility</h4></div>
<div class="ant-card ant-card-bordered">
  <div class="ant-card-head"><div class="ant-card-head-title"><b>Eligibility Criteria #1</b></div></div>
  <div class="ant-card-body">
    <div class="ant-form-item"><div class="ant-form-item-label"><label for="e_min">Minimum Age</label></div><input id="e_min" name="eligibility_min_age" class="ant-input" type="number"></div>
    <div class="ant-form-item"><div class="ant-form-item-label"><label for="e_max">Maximum Age</label></div><input id="e_max" name="eligibility_max_age" class="ant-input" type="number"></div>
    <div class="ant-radio-group">
      <label class="ant-radio-wrapper"><span class="ant-radio"><input id="e_male" type="radio" value="male" name="e_sex"></span><span class="ant-radio-label">Male</span></label>
      <label class="ant-radio-wrapper"><span class="ant-radio"><input id="e_female" type="radio" value="female" name="e_sex"></span><span class="ant-radio-label">Female</span></label>
    </div>
  </div>
</div>
<div style="margin-top:40px"><h4>Recommendation</h4>
  <div class="ant-card ant-card-bordered">
    <div class="ant-card-head"><div class="ant-card-head-title"><b>Recommendation Criteria #1</b></div></div>
    <div class="ant-card-body">
      <div class="ant-form-item"><div class="ant-form-item-label"><label for="r_min">Minimum Age</label></div><input id="r_min" name="recommendation_min_age" class="ant-input" type="number"></div>
      <div class="ant-form-item"><div class="ant-form-item-label"><label for="r_max">Maximum Age</label></div><input id="r_max" name="recommendation_max_age" class="ant-input" type="number"></div>
      <div class="ant-radio-group">
        <label class="ant-radio-wrapper"><span class="ant-radio"><input id="r_male" type="radio" value="male" name="r_sex"></span><span class="ant-radio-label">Male</span></label>
        <label class="ant-radio-wrapper"><span class="ant-radio"><input id="r_female" type="radio" value="female" name="r_sex"></span><span class="ant-radio-label">Female</span></label>
      </div>
    </div>
  </div>
</div>
</form>
"""


@pytest.mark.playwright
def test_sectioned_inputs_and_radios_land_in_named_section() -> None:
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
                await page.set_content(_TWO_SECTION_FORM)
                for s in (
                    'Enter "20" into Eligibility Minimum Age',
                    'Enter "90" into Eligibility Maximum Age',
                    'Select "Male" radio button for Eligibility',
                    'Enter "30" into Recommendation Minimum Age',
                    'Enter "80" into Recommendation Maximum Age',
                ):
                    await sdk.act(s, channel="web", page=page)
                return {
                    "e_min": await page.locator("#e_min").input_value(),
                    "r_min": await page.locator("#r_min").input_value(),
                    "e_max": await page.locator("#e_max").input_value(),
                    "r_max": await page.locator("#r_max").input_value(),
                    "e_male": await page.locator("#e_male").is_checked(),
                    "r_male": await page.locator("#r_male").is_checked(),
                }
            finally:
                await browser.close()
        finally:
            await pw.stop()

    r = asyncio.run(go())
    assert r["e_min"] == "20" and r["e_max"] == "90"      # Eligibility values stay put
    assert r["r_min"] == "30" and r["r_max"] == "80"      # Recommendation not written to Eligibility
    assert r["e_male"] is True and r["r_male"] is False    # radio hit the right section
