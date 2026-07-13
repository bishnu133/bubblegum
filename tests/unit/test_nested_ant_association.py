"""Regression: label→control association in deeply-nested / grouped Ant layouts.

Two field patterns that broke because a *control-internal* label (a checkbox's
own ``<label>``, a Quill toolbar's ``.ql-picker-label``, …) or a bare group
heading was mistaken for — or hid — the field's real label:

1. A date **range** whose picker is nested inside a form-item that also holds a
   ``No … end date`` checkbox. "no registration **end date**" bled into the
   picker's label, so "Challenge **End date**" scored higher on the *Registration*
   picker and the two ranges overwrote each other.
2. A dropdown introduced by a bare ``<span>Eligibility Tags</span>`` heading
   (not a ``<label for>``), sitting above a *group* of two selects. With no
   matching form label the resolver fell onto the nearest labelled select
   ("Challenges Joined").

Both are exercised against a real browser; the tests skip when none is available.
"""
from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright import adapter as A


def _browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        browser = pw.chromium.launch()
    except Exception as exc:  # pragma: no cover
        pw.stop()
        pytest.skip(f"No usable browser binary: {exc}")
    return pw, browser


# Two enabled range pickers. The Registration picker is nested inside a form-item
# that also contains a "No registration end date" checkbox (its own <label>).
_DATE_FORM = """
<form>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label"><label title="Challenge Period">Challenge Period</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
      <div class="ant-picker ant-picker-range">
        <div class="ant-picker-input"><input data-testid="date-range-picker" placeholder="Start date" date-range="start" value="2026/07/15 00:00"></div>
        <div class="ant-picker-input"><input data-testid="date-range-picker" placeholder="End date" date-range="end" value="2026/07/31 00:00"></div>
      </div></div></div></div>
  </div></div>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label"><label title="Registration Period">Registration Period</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
      <div class="ant-form-item"><div class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
        <label class="ant-checkbox-wrapper"><span class="ant-checkbox"><input type="checkbox"><span class="ant-checkbox-inner"></span></span><span class="ant-checkbox-label">No registration end date</span></label>
      </div></div></div></div></div>
      <div class="ant-form-item"><div class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
        <div class="ant-picker ant-picker-range">
          <div class="ant-picker-input"><input data-testid="date-range-picker" placeholder="Start date" date-range="start" value="2026/07/14 00:00"></div>
          <div class="ant-picker-input"><input data-testid="date-range-picker" placeholder="End date" date-range="end" value="2026/07/30 00:00"></div>
        </div></div></div></div></div></div>
    </div></div></div></div>
  </div></div>
</form>
"""


@pytest.mark.playwright
def test_date_range_pickers_do_not_cross_contaminate() -> None:
    """Each Challenge/Registration start/end resolves to its OWN picker input."""
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(_DATE_FORM)

        def resolve(which, phrase):
            sel = page.evaluate(A._FIND_DATE_RANGE_JS, {"which": which, "phrase": phrase})
            assert sel, f"no date input for {which} {phrase!r}"
            return page.locator(sel["selector"]).get_attribute("value")

        got = {
            "cs": resolve("start", "Challenge Start date"),
            "ce": resolve("end", "Challenge End date"),
            "rs": resolve("start", "Registration Start date"),
            "re": resolve("end", "Registration End date"),
        }
    finally:
        browser.close()
        pw.stop()

    # Challenge picker: 07/15 – 07/31 ; Registration picker: 07/14 – 07/30.
    assert got["cs"] == "2026/07/15 00:00"
    assert got["ce"] == "2026/07/31 00:00", f"Challenge End leaked to another picker: {got['ce']}"
    assert got["rs"] == "2026/07/14 00:00"
    assert got["re"] == "2026/07/30 00:00"


# A dropdown group introduced by a bare <span> heading, above two selects: a
# compact qualifier ("All") and the multi-select value picker.
_TAGS_FORM = """
<form>
  <div class="ant-form-item"><div class="ant-row ant-form-item-row">
    <div class="ant-col ant-form-item-label"><label for="chJoined" title="Challenges Joined">Challenges Joined</label></div>
    <div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
      <div class="ant-select ant-select-multiple ant-select-show-arrow" data-testid="challenge-membership-select" style="width:100%">
        <div class="ant-select-selector"><span class="ant-select-selection-search"><input id="chJoined" class="ant-select-selection-search-input" role="combobox" type="search" readonly></span></div>
        <span class="ant-select-arrow"></span></div>
    </div></div></div></div>
  </div></div>
  <span>Eligibility Tags</span>
  <div style="margin-top:10px"><div class="ant-form-item"><div class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
    <span class="ant-input-group" style="display:flex">
      <div class="ant-form-item" style="width:100px"><div class="ant-row ant-form-item-row"><div class="ant-col ant-form-item-control"><div class="ant-form-item-control-input"><div class="ant-form-item-control-input-content">
        <div class="ant-select ant-select-single ant-select-show-arrow" data-testid="tag-subtype" style="width:100%">
          <div class="ant-select-selector"><span class="ant-select-selection-search"><input class="ant-select-selection-search-input" role="combobox" type="search" readonly></span><span class="ant-select-selection-item" title="All">All</span></div>
          <span class="ant-select-arrow"></span></div>
      </div></div></div></div></div>
      <div class="ant-select ant-select-multiple ant-select-show-arrow" data-testid="tag-value" style="min-width:70%;flex-grow:1">
        <div class="ant-select-selector"><span class="ant-select-selection-search"><input class="ant-select-selection-search-input" role="combobox" type="search"></span></div>
        <span class="ant-select-arrow"></span></div>
    </span>
  </div></div></div></div></div></div>
</form>
"""


@pytest.mark.playwright
def test_group_heading_select_not_hijacked_by_neighbour() -> None:
    """"Eligibility Tags" (a bare heading) resolves to its value picker, not the
    neighbouring labelled "Challenges Joined" select."""
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_content(_TAGS_FORM)

        def testid(phrase, value):
            res = page.evaluate(A._FIND_SELECT_TRIGGER_JS, {"phrase": phrase, "value": value})
            assert res, f"no select for {phrase!r}"
            return page.locator(res["selector"]).evaluate(
                "e => (e.closest('.ant-select') || e).getAttribute('data-testid')"
            )

        tags = testid("Eligibility Tags", "GaqAccepted")
        joined = testid("Challenges Joined", "")
    finally:
        browser.close()
        pw.stop()

    assert tags == "tag-value", f"Eligibility Tags resolved to {tags!r}"
    assert joined == "challenge-membership-select"
