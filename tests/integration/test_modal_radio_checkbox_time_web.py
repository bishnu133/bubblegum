"""Feature: radio/checkbox/time-field resolution inside a blocking modal, plus
exact-label preference for radios and checkboxes.

Reproduces three real failures on an Ant-style form:

1. ``Select "Required" radio`` used to select "Not Required" — the phrase
   "Required" is a whole word in BOTH labels, so option scoring tied and DOM
   order decided. The resolver now prefers the option whose visible label has the
   fewest EXTRA words, so the exact "Required" wins.

2. A checkbox inside an open modal ("Mon") must resolve to the modal's control,
   never to a same-labelled checkbox on the page behind the mask.

3. A "Start time" / "End time" field inside a modal must NOT be hijacked by a
   date **range** picker on the page behind the modal. The range resolver is now
   scoped to the open dialog and yields nothing when the dialog has no range
   picker, so the input finder claims the modal's time field instead.

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter


# A page with a "Required" / "Not Required" radio group (the exact-label trap).
_RADIO_PAGE = """
<!doctype html><html><body style="font-family:Helvetica">
  <form><h3>GAQ requirement</h3>
    <label class="ant-radio-wrapper"><span class="ant-radio">
      <input type="radio" name="gaq" value="notrequired" id="gaq-0"></span>
      <span class="ant-radio-label">Not Required</span></label>
    <label class="ant-radio-wrapper"><span class="ant-radio">
      <input type="radio" name="gaq" value="required" id="gaq-1"></span>
      <span class="ant-radio-label">Required</span></label>
  </form>
</body></html>
"""

# Mirrors the real Ant "Add Sessions" modal: a date RANGE picker on the page
# behind the mask (the Activity Period), and INSIDE the modal BOTH a date range
# picker ("Creating session(s) from") and a *time* range picker (Start time / End
# time) — so the resolver must pick the modal's TIME range, not the background
# picker and not the modal's own date range. Plus a "Mon" checkbox in each place.
_MODAL_PAGE = """
<!doctype html><html><body style="font-family:Helvetica">
  <div id="root"><form id="bg-form">
    <label class="ant-checkbox-wrapper"><span class="ant-checkbox">
      <input type="checkbox" id="bg-mon"></span><span>Mon</span></label>
    <div class="ant-picker ant-picker-range">
      <input date-range="start" id="activityStart" placeholder="Start date">
      <input date-range="end" id="activityEnd" placeholder="End date">
    </div>
  </form></div>
  <div class="ant-modal-root"><div class="ant-modal-mask"></div>
    <div class="ant-modal-wrap"><div role="dialog" aria-modal="true" class="ant-modal" style="z-index:1000">
      <div class="ant-modal-content">
        <div class="ant-modal-header">Add Sessions</div>
        <div class="ant-modal-body"><form id="session-form">
          <div class="ant-form-item"><div class="ant-form-item-label"><label>Creating session(s) from</label></div>
            <div class="ant-picker ant-picker-range">
              <input date-range="start" id="sessionDateStart" placeholder="Start date">
              <input date-range="end" id="sessionDateEnd" placeholder="End date">
            </div></div>
          <div class="ant-form-item"><div class="ant-form-item-label"><label>Session time</label></div>
            <div class="ant-picker ant-picker-range">
              <input date-range="start" id="sessionTimeStart" placeholder="Start time">
              <input date-range="end" id="sessionTimeEnd" placeholder="End time">
            </div></div>
          <label class="ant-checkbox-wrapper"><span class="ant-checkbox">
            <input type="checkbox" id="m-mon"></span><span>Mon</span></label>
        </form></div>
        <div class="ant-modal-footer"><button type="button">Add</button></div>
      </div></div></div></div>
</body></html>
"""


async def _launch(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        return await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")


async def _page(p, html):
    browser = await _launch(p)
    page = await browser.new_page()
    await page.set_content(html)
    return browser, page


async def test_radio_prefers_exact_label_over_superset():
    """`Select "Required"` must pick the exact option, not "Not Required"."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _RADIO_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            res = await adapter.find_radio("Required", "in GAQ requirement section")
            assert res, "no radio resolved"
            await page.click(res["selector"])
            checked = await page.eval_on_selector("#gaq-1", "e => e.checked")
            other = await page.eval_on_selector("#gaq-0", "e => e.checked")
            assert checked is True, f"exact 'Required' not selected (name={res.get('name')!r})"
            assert other is False, "'Not Required' was wrongly selected"
        finally:
            await browser.close()


async def test_radio_can_still_select_not_required():
    """The superset label is still reachable when it is the one named."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _RADIO_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            res = await adapter.find_radio("Not Required", "in GAQ requirement section")
            assert res
            await page.click(res["selector"])
            assert await page.eval_on_selector("#gaq-0", "e => e.checked") is True
            assert await page.eval_on_selector("#gaq-1", "e => e.checked") is False
        finally:
            await browser.close()


async def test_checkbox_targets_modal_not_background():
    """A "Mon" checkbox resolves inside the open modal, not the background copy."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _MODAL_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            res = await adapter.find_checkbox("Mon", 'Select "Mon" checkbox')
            assert res, "no checkbox resolved"
            await page.click(res["selector"])
            assert await page.eval_on_selector("#m-mon", "e => e.checked") is True, "modal checkbox not toggled"
            assert await page.eval_on_selector("#bg-mon", "e => e.checked") is False, "background checkbox wrongly toggled"
        finally:
            await browser.close()


async def test_time_range_in_modal_wins_over_background_and_date_range():
    """With the modal open, "Activity Start time" resolves to the modal's TIME
    range start — not the background Activity Period picker (behind the mask) and
    not the modal's own "Creating session(s) from" DATE range."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _MODAL_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_date_range_input("start", "Activity Start time")
            assert ref, "no range input resolved"
            which = await page.eval_on_selector(ref, "e => e.id")
            assert which == "sessionTimeStart", (
                f"resolved to {which!r}, expected the modal's time-range start"
            )
        finally:
            await browser.close()


async def test_end_time_range_in_modal_resolves_to_time_end():
    """The end side likewise lands on the modal's time-range end input."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _MODAL_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_date_range_input("end", "Activity End time")
            assert ref, "no range input resolved"
            which = await page.eval_on_selector(ref, "e => e.id")
            assert which == "sessionTimeEnd", f"resolved to {which!r}, expected time-range end"
        finally:
            await browser.close()


async def test_date_range_in_modal_still_resolves_to_date_when_named():
    """A phrase naming a DATE side still lands on the modal's date range, proving
    the placeholder tiebreak separates the two range pickers both ways."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _MODAL_PAGE)
        try:
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_date_range_input("start", "session start date")
            assert ref, "no range input resolved"
            which = await page.eval_on_selector(ref, "e => e.id")
            assert which == "sessionDateStart", f"resolved to {which!r}, expected the date-range start"
        finally:
            await browser.close()


async def test_daterange_still_works_without_modal():
    """No modal open: the period range picker resolves as before (no regression)."""
    aw = pytest.importorskip("playwright.async_api")
    _NO_MODAL = """
    <!doctype html><html><body><form>
      <div class="ant-picker ant-picker-range">
        <input date-range="start" data-testid="p-start" placeholder="Start date">
        <input date-range="end" data-testid="p-end" placeholder="End date">
      </div></form></body></html>
    """
    async with aw.async_playwright() as p:
        browser, page = await _page(p, _NO_MODAL)
        try:
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_date_range_input("start", "Activity Start date")
            assert ref, "range picker not resolved without a modal"
            which = await page.eval_on_selector(ref, "e => e.getAttribute('data-testid')")
            assert which == "p-start"
        finally:
            await browser.close()
