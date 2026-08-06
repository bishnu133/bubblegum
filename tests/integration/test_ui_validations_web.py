"""Feature: generic, selector-free UI validations + row-scoped table actions.

Covers six additions, all framework-agnostic (native / Ant / MUI), driven by
plain-English steps:

  V1  element-present  — verify('the "Save" button is present' / 'a table is present')
  V2  active/highlight  — verify('the "Activities" menu is highlighted')
  V3  dropdown options  — verify('the "Programme" dropdown contains "A","B"')
  V4  alert text        — verify('the alert description contains "..."')
  V5  page header       — verify('the page header is "General Information"')
  V6  row-scoped action — act('In the row where Date is "10/08/2026", select the checkbox')

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum import act, verify, configure_runtime

_PAGE = """
<!doctype html><html><body style="font-family:Helvetica">
  <nav class="ant-menu">
    <div class="ant-menu-item ant-menu-item-selected" role="menuitem" aria-current="page"
         style="font-weight:700">Activities</div>
    <div class="ant-menu-item" role="menuitem" style="font-weight:400">Reports</div>
  </nav>

  <h1>General Information</h1>

  <div role="alert" class="ant-alert ant-alert-info">
    <div class="ant-alert-message">Let participants know what to expect</div>
    <div class="ant-alert-description">Example: A cardio dance workout that combines Kpop music.</div>
  </div>

  <form>
    <label for="prog">Programme</label>
    <select id="prog">
      <option>Automation Smoke Prog HPB</option>
      <option>Wellness Programme</option>
      <option>Steps Challenge</option>
    </select>
    <button type="button">Save</button>
  </form>

  <div class="ant-table"><div class="ant-table-container"><div class="ant-table-content">
    <table>
      <thead class="ant-table-thead"><tr>
        <th class="ant-table-selection-column"></th><th>Date</th><th>Day</th><th>Assessments</th>
      </tr></thead>
      <tbody class="ant-table-tbody">
        <tr data-row-key="0"><td><label class="ant-checkbox-wrapper"><span class="ant-checkbox">
            <input type="checkbox" id="cb0"></span></label></td>
          <td>07/08/2026</td><td>Friday</td><td><a id="asmt0">Add Assessment</a></td></tr>
        <tr data-row-key="1"><td><label class="ant-checkbox-wrapper"><span class="ant-checkbox">
            <input type="checkbox" id="cb1"></span></label></td>
          <td>10/08/2026</td><td>Monday</td><td><a id="asmt1">Add Assessment</a></td></tr>
      </tbody>
    </table>
  </div></div></div>
</body></html>
"""


async def _page(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(_PAGE)
    configure_runtime()
    return browser, page


# --- V1: element present -----------------------------------------------------

async def test_named_button_present():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify('the "Save" button is present', channel="web", page=page)
            assert r.status == "passed", r.error and r.error.message
        finally:
            await browser.close()


async def test_table_present_and_missing_button():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify("a table is present on the page", channel="web", page=page)
            assert r.status == "passed"
            r2 = await verify('the "Delete" button is present', channel="web", page=page)
            assert r2.status == "failed"
        finally:
            await browser.close()


# --- V2: active / highlighted ------------------------------------------------

async def test_menu_highlighted_and_not():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify('the "Activities" menu is highlighted', channel="web", page=page)
            assert r.status == "passed", r.error and r.error.message
            r2 = await verify('the "Reports" menu is highlighted', channel="web", page=page)
            assert r2.status == "failed"
        finally:
            await browser.close()


# --- V3: dropdown options ----------------------------------------------------

async def test_dropdown_contains_options():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify(
                'the "Programme" dropdown contains "Wellness Programme", "Steps Challenge"',
                channel="web", page=page,
            )
            assert r.status == "passed", r.error and r.error.message
            r2 = await verify('the "Programme" dropdown contains "Nonexistent Option"',
                              channel="web", page=page)
            assert r2.status == "failed"
        finally:
            await browser.close()


# --- V4: alert description ---------------------------------------------------

async def test_alert_description():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify('the alert description contains "cardio dance workout"',
                             channel="web", page=page)
            assert r.status == "passed", r.error and r.error.message
        finally:
            await browser.close()


# --- V5: page header ---------------------------------------------------------

async def test_page_header():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await verify('the page header is "General Information"', channel="web", page=page)
            assert r.status == "passed", r.error and r.error.message
            r2 = await verify('the page header is "Date and Time"', channel="web", page=page)
            assert r2.status == "failed"
        finally:
            await browser.close()


# --- V6: row-scoped checkbox + link ------------------------------------------

async def test_row_checkbox_by_matching_value():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            r = await act('In the row where Date is "10/08/2026", select the checkbox',
                          channel="web", page=page)
            assert r.status in ("passed", "recovered"), r.error and r.error.message
            assert await page.eval_on_selector("#cb1", "e => e.checked") is True
            assert await page.eval_on_selector("#cb0", "e => e.checked") is False
        finally:
            await browser.close()


async def test_row_link_by_matching_value():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            # Tag the two same-text links so we can tell which one was clicked.
            await page.eval_on_selector("#asmt0", "e => e.addEventListener('click', ev=>{ev.preventDefault(); window.__clicked='row0';})")
            await page.eval_on_selector("#asmt1", "e => e.addEventListener('click', ev=>{ev.preventDefault(); window.__clicked='row1';})")
            r = await act('In the row where Date is "10/08/2026", click the "Add Assessment" link',
                          channel="web", page=page)
            assert r.status in ("passed", "recovered"), r.error and r.error.message
            which = await page.evaluate("() => window.__clicked")
            assert which == "row1", f"clicked {which}, expected the 10/08 row's link"
        finally:
            await browser.close()
