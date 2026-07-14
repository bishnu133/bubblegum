"""Section-aware radio/checkbox resolution.

Two form sections ("Eligibility" and "Recommendation") frequently carry the same
option labels — Male/Female radios, identical tag dropdowns. Selecting "Male …
for Eligibility" must land in the Eligibility section, not fall to DOM order and
click the Recommendation copy. The resolvers take the surrounding instruction as
*context* and match its non-option words against the nearest section heading (an
Ant card head-title, a <legend>/<hN>, …), a bounded tiebreak that never overrides
which OPTION is chosen — only which of two equally-matching sections it lives in.

A second, subtler trap this covers: the option label "male" is a *substring* of
"female", so substring matching would tie every Male query with the adjacent
Female radio. The resolvers match whole words instead.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


# --- _call_dom_finder: context passed only to finders that accept it ---------

def test_call_dom_finder_passes_context_when_supported():
    calls = []

    async def two_arg(text, context):
        calls.append((text, context))
        return {"selector": "x"}

    _run(sdk._call_dom_finder(two_arg, "Male", "for Eligibility"))
    assert calls == [("Male", "for Eligibility")]


def test_call_dom_finder_omits_context_for_single_arg_finder():
    calls = []

    async def one_arg(text):                      # legacy single-arg finder
        calls.append(text)
        return {"selector": "x"}

    _run(sdk._call_dom_finder(one_arg, "Male", "for Eligibility"))
    assert calls == ["Male"]                      # not called with 2 args


def test_radio_resolver_forwards_instruction_as_context():
    seen = {}

    class _Adapter:
        async def find_radio(self, phrase, context=""):
            seen["phrase"], seen["context"] = phrase, context
            return {"selector": '[data-bg-radio="1"]', "checked": False,
                    "name": "male", "section": "eligibility criteria #1"}

    intent = StepIntent(instruction='Select "Male" radio button for Eligibility',
                        channel="web", action_type="select", target_phrase=None,
                        input_value=None, context={})
    t = _run(sdk._maybe_resolve_radio(_Adapter(), "web", intent))
    assert t is not None and t.resolver_name == "radio_dom"
    assert seen["phrase"] == "Male"
    assert "eligibility" in seen["context"].lower()   # section context reached the finder


# --- browser: real two-section DOM, shared Male/Female labels ----------------

_TWO_SECTIONS = """
<form class="ant-form">
  <div style="margin-top:60px"><h4>Eligibility</h4></div>
  <div class="ant-card ant-card-bordered">
    <div class="ant-card-head"><div class="ant-card-head-title"><b>Eligibility Criteria #1</b></div></div>
    <div class="ant-card-body">
      <div class="ant-radio-group">
        <label class="ant-radio-wrapper ant-radio-wrapper-checked"><span class="ant-radio ant-radio-checked"><input id="elig_all" class="ant-radio-input" type="radio" value="all" checked name="e_gender"></span><span class="ant-radio-label">All</span></label>
        <label class="ant-radio-wrapper"><span class="ant-radio"><input id="elig_male" class="ant-radio-input" type="radio" value="male" name="e_gender"></span><span class="ant-radio-label">Male</span></label>
        <label class="ant-radio-wrapper"><span class="ant-radio"><input id="elig_female" class="ant-radio-input" type="radio" value="female" name="e_gender"></span><span class="ant-radio-label">Female</span></label>
      </div>
    </div>
  </div>
  <div style="margin-top:60px"><h4>Recommendation</h4>
    <div class="ant-card ant-card-bordered">
      <div class="ant-card-head"><div class="ant-card-head-title"><b>Recommendation Criteria #1</b></div></div>
      <div class="ant-card-body">
        <div class="ant-radio-group">
          <label class="ant-radio-wrapper ant-radio-wrapper-checked"><span class="ant-radio ant-radio-checked"><input id="reco_na" class="ant-radio-input" type="radio" value="NA" checked name="r_gender"></span><span class="ant-radio-label">NA</span></label>
          <label class="ant-radio-wrapper"><span class="ant-radio"><input id="reco_male" class="ant-radio-input" type="radio" value="male" name="r_gender"></span><span class="ant-radio-label">Male</span></label>
          <label class="ant-radio-wrapper"><span class="ant-radio"><input id="reco_female" class="ant-radio-input" type="radio" value="female" name="r_gender"></span><span class="ant-radio-label">Female</span></label>
        </div>
      </div>
    </div>
  </div>
</form>
"""


_GENERIC_HEADINGS = """
<form class="ant-form">
  <div class="ant-card"><div class="ant-card-head"><div class="ant-card-head-title">Criteria #1</div></div><div class="ant-card-body">
    <div class="ant-radio-group" id="eligibilityRuleGroups_0_eligibilityRules_gender">
      <label class="ant-radio-wrapper"><input id="eligibilityRules_all" type="radio" value="all" name="0_eligibilityRules_gender"><span class="ant-radio-label">All</span></label>
      <label class="ant-radio-wrapper"><input id="eligibilityRules_male" type="radio" value="male" name="0_eligibilityRules_gender"><span class="ant-radio-label">Male</span></label>
      <label class="ant-radio-wrapper"><input id="eligibilityRules_female" type="radio" value="female" name="0_eligibilityRules_gender"><span class="ant-radio-label">Female</span></label>
    </div></div></div>
  <div class="ant-card"><div class="ant-card-head"><div class="ant-card-head-title">Criteria #1</div></div><div class="ant-card-body">
    <div class="ant-radio-group" id="recommendationRuleGroups_0_recommendationRules_gender">
      <label class="ant-radio-wrapper"><input id="recommendationRules_NA" type="radio" value="NA" name="0_recommendationRules_gender"><span class="ant-radio-label">NA</span></label>
      <label class="ant-radio-wrapper"><input id="recommendationRules_male" type="radio" value="male" name="0_recommendationRules_gender"><span class="ant-radio-label">Male</span></label>
      <label class="ant-radio-wrapper"><input id="recommendationRules_female" type="radio" value="female" name="0_recommendationRules_gender"><span class="ant-radio-label">Female</span></label>
    </div></div></div>
</form>
"""


_ANT_CARD_TITLE_ONLY = """
<form class="ant-form">
  <div class="ant-card ant-card-bordered">
    <div class="ant-card-head"><div class="ant-card-head-wrapper"><div class="ant-card-head-title"><b>Eligibility Criteria #1</b></div><div class="ant-card-extra"><button type="button" class="ant-btn"><span>Remove</span></button></div></div></div>
    <div class="ant-card-body">
      <div class="ant-form-item"><div class="ant-form-item-label"><label>Sex</label></div>
        <div class="ant-radio-group" role="radiogroup">
          <label class="ant-radio-wrapper ant-radio-wrapper-checked"><span class="ant-radio ant-radio-checked"><input id="rc_radio_1" type="radio" value="all" checked name="0_gender"></span><span class="ant-radio-label">All</span></label>
          <label class="ant-radio-wrapper"><span class="ant-radio"><input id="rc_radio_2" type="radio" value="male" name="0_gender"></span><span class="ant-radio-label">Male</span></label>
          <label class="ant-radio-wrapper"><span class="ant-radio"><input id="rc_radio_3" type="radio" value="female" name="0_gender"></span><span class="ant-radio-label">Female</span></label>
        </div>
      </div>
    </div>
  </div>
  <div style="margin-top:20px"><h4>Recommendation</h4>
    <div class="ant-card ant-card-bordered">
      <div class="ant-card-head"><div class="ant-card-head-wrapper"><div class="ant-card-head-title"><b>Recommendation Criteria #1</b></div></div></div>
      <div class="ant-card-body">
        <div class="ant-form-item"><div class="ant-form-item-label"><label>Sex</label></div>
          <div class="ant-radio-group" role="radiogroup">
            <label class="ant-radio-wrapper ant-radio-wrapper-checked"><span class="ant-radio ant-radio-checked"><input id="rc_radio_7" type="radio" value="NA" checked name="1_gender"></span><span class="ant-radio-label">NA</span></label>
            <label class="ant-radio-wrapper"><span class="ant-radio"><input id="rc_radio_8" type="radio" value="male" name="1_gender"></span><span class="ant-radio-label">Male</span></label>
            <label class="ant-radio-wrapper"><span class="ant-radio"><input id="rc_radio_9" type="radio" value="female" name="1_gender"></span><span class="ant-radio-label">Female</span></label>
          </div>
        </div>
      </div>
    </div>
  </div>
</form>
"""


def _deep_radio_group(prefix, options):
    # Realistic Ant nesting: form-item > row > col > control > control-input >
    # content > radio-group > space > space-item > wrapper > radio > input.
    items = ""
    for oid, label, val, checked in options:
        wc = " ant-radio-wrapper-checked" if checked else ""
        rc = " ant-radio-checked" if checked else ""
        chk = " checked" if checked else ""
        items += (
            f'<div class="ant-space-item"><label class="ant-radio-wrapper{wc}">'
            f'<span class="ant-radio{rc}"><input id="{oid}" class="ant-radio-input" type="radio" value="{val}"{chk} name="{prefix}_gender"></span>'
            f'<span class="ant-radio-label">{label}</span></label></div>'
        )
    return (
        '<div class="ant-form-item ant-form-item-vertical"><div class="ant-row ant-form-item-row">'
        '<div class="ant-col ant-form-item-label"><label>Sex</label></div>'
        '<div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input">'
        '<div class="ant-form-item-control-input-content">'
        f'<div class="ant-radio-group" role="radiogroup"><div class="ant-space ant-space-horizontal">{items}</div></div>'
        '</div></div></div></div></div>'
    )


_DEEP_CARDS = (
    '<form class="ant-form ant-form-vertical">'
    '<div class="ant-card ant-card-bordered"><div class="ant-card-head"><div class="ant-card-head-wrapper">'
    '<div class="ant-card-head-title"><b>Eligibility Criteria #1</b></div>'
    '<div class="ant-card-extra"><button type="button" class="ant-btn"><span>Remove</span></button></div></div></div>'
    '<div class="ant-card-body">'
    + _deep_radio_group("elig", [("rc_radio_1", "All", "all", True), ("rc_radio_2", "Male", "male", False), ("rc_radio_3", "Female", "female", False)])
    + '</div></div>'
    '<div style="margin-top:40px"><h4>Recommendation</h4>'
    '<div class="ant-card ant-card-bordered"><div class="ant-card-head"><div class="ant-card-head-wrapper">'
    '<div class="ant-card-head-title"><b>Recommendation Criteria #1</b></div></div></div>'
    '<div class="ant-card-body">'
    + _deep_radio_group("reco", [("rc_radio_7", "NA", "NA", True), ("rc_radio_8", "Male", "male", False), ("rc_radio_9", "Female", "female", False)])
    + '</div></div></div></form>'
)


@pytest.mark.playwright
def test_radio_section_works_at_realistic_ant_nesting_depth() -> None:
    # The real form nests the radio ~12 levels below its .ant-card. Section
    # detection must find the card title at ANY depth (via closest), not a bounded
    # ancestor climb — the a42 failure, where the climb stopped short of the card.
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
                await page.set_content(_DEEP_CARDS)
                depth = await page.evaluate(
                    "() => { let e=document.getElementById('rc_radio_2'), n=0;"
                    " while (e && !(e.matches && e.matches('.ant-card'))) { e=e.parentElement; n++; } return n; }"
                )
                await sdk.act('Select "Male" radio button for Eligibility', channel="web", page=page)
                return depth, await page.locator("#rc_radio_2").is_checked(), await page.locator("#rc_radio_8").is_checked()
            finally:
                await browser.close()
        finally:
            await pw.stop()

    depth, elig_male, reco_male = asyncio.run(go())
    assert depth >= 10                       # genuinely deep nesting
    assert elig_male is True and reco_male is False


@pytest.mark.playwright
def test_radio_section_from_ant_card_title_with_generic_ids() -> None:
    # The real EDSH form: generic radio ids (rc_radio_*), a shared "Sex" label,
    # and the ONLY discriminating word in the Ant card head-title ("Eligibility
    # Criteria #1"). Section detection must read that title, else DOM order picks
    # the later (Recommendation) Male — the a41 failure.
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
                await page.set_content(_ANT_CARD_TITLE_ONLY)
                await sdk.act('Select "Male" radio button for Eligibility', channel="web", page=page)
                return (
                    await page.locator("#rc_radio_2").is_checked(),   # Eligibility Male
                    await page.locator("#rc_radio_8").is_checked(),   # Recommendation Male
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    elig_male, reco_male = asyncio.run(go())
    assert elig_male is True and reco_male is False


@pytest.mark.playwright
def test_radio_section_disambiguated_by_id_when_headings_are_generic() -> None:
    # The section word may be absent from the heading and live only in the
    # control's id/name ("eligibilityRules_male"). That signal must still pin the
    # right section — headings alone are not enough.
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
                await page.set_content(_GENERIC_HEADINGS)
                ad = PlaywrightAdapter(page)

                async def rid(phrase, ctx):
                    r = await ad.find_radio(phrase, ctx)
                    return await page.locator(r["selector"]).locator("input").first.get_attribute("id")

                return (
                    await rid("Male", 'Select "Male" radio button for Eligibility'),
                    await rid("Male", 'Select "Male" radio button for Recommendation Sex'),
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    e, r = asyncio.run(go())
    assert e == "eligibilityRules_male"
    assert r == "recommendationRules_male"


@pytest.mark.playwright
def test_radio_lands_in_named_section_not_dom_order() -> None:
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
                await page.set_content(_TWO_SECTIONS)

                async def is_checked(rid):
                    return await page.locator(f"#{rid}").is_checked()

                s1 = await sdk.act('Select "Male" radio button for Eligibility', channel="web", page=page)
                s2 = await sdk.act('Select "Male" radio button for Recommendation Sex', channel="web", page=page)
                return (
                    s1.status, await is_checked("elig_male"), await is_checked("reco_male"),
                    s2.status, await is_checked("reco_male"),
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    s1, elig_male, reco_male_after1, s2, reco_male = asyncio.run(go())
    assert (s1, s2) == ("passed", "passed")
    assert elig_male is True            # Eligibility step hit the Eligibility Male
    assert reco_male_after1 is False    # …and did NOT touch the Recommendation copy
    assert reco_male is True            # Recommendation step then hit its own Male
