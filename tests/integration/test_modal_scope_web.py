"""Feature: when a blocking modal is open, `type` and `upload` steps resolve
inside the modal — never onto a same-named field on the page behind the mask.

Reproduces the real failure: a workout form (with its own "Description" textarea
and "Image" file input) opens an "Add safety disclaimer" modal that also has a
"Description" textarea and an "Image" upload. `Enter … into Description` used to
land in the background field (or nowhere visible); the upload hit the wrong file
input. Resolution is now scoped to the topmost open (blocking) modal, falling
back to the document when no modal is up.

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

# Background form + an Ant-style blocking modal, each with a "Description"
# textarea and an "Image" file input.
_MODAL_PAGE = """
<!doctype html><html><body style="font-family:Helvetica">
  <div id="root"><form id="workout-form">
    <div class="ant-form-item"><div class="ant-form-item-label"><label>Description</label></div>
      <textarea data-testid="bg-desc" class="ant-input"></textarea></div>
    <div class="ant-form-item"><div class="ant-form-item-label"><label>Image</label></div>
      <input type="file" data-testid="bg-file"></div>
  </form></div>
  <div class="ant-modal-root"><div class="ant-modal-mask"></div>
    <div class="ant-modal-wrap"><div role="dialog" aria-modal="true" class="ant-modal" style="z-index:1000">
      <div class="ant-modal-content">
        <div class="ant-modal-header">Add safety disclaimer</div>
        <div class="ant-modal-body" style="height:55vh;overflow-y:scroll"><form id="safety-disclaimer-form">
          <div class="ant-form-item"><div class="ant-form-item-label"><label>Title</label></div>
            <input data-testid="m-title" class="ant-input"></div>
          <div class="ant-form-item"><div class="ant-form-item-label"><label>Description</label></div>
            <textarea data-testid="txt-disclaimer-description" rows="6" maxlength="200" class="ant-input"></textarea></div>
          <div class="ant-form-item" data-testid="workout-asset-uploader">
            <div class="ant-form-item-label"><label>Image</label></div>
            <span class="ant-upload-wrapper"><div class="ant-upload ant-upload-select">
              <span class="ant-upload"><input type="file" data-testid="m-file"></span></div></span></div>
        </form></div>
        <div class="ant-modal-footer"><button type="button">Add</button></div>
      </div></div></div></div>
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
    await page.set_content(_MODAL_PAGE)
    return browser, page


async def test_type_targets_modal_field_not_background():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act('Enter "DISCLAIMER-TEXT" into Description', channel="web", page=page)
            bg = await page.eval_on_selector('[data-testid=bg-desc]', 'e=>e.value')
            modal = await page.eval_on_selector('[data-testid=txt-disclaimer-description]', 'e=>e.value')
            assert res.status in ("passed", "recovered"), res.status
            assert modal == "DISCLAIMER-TEXT", f"modal textarea not filled (background={bg!r})"
            assert bg == "", "background textarea was wrongly filled"
        finally:
            await browser.close()


async def test_upload_targets_modal_file_input_not_background():
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_file_input("disclaimer Image")
            assert ref, "no file input resolved"
            which = await page.eval_on_selector(ref, "e => e.getAttribute('data-testid')")
            assert which == "m-file", f"upload resolved to {which}, expected the modal's m-file"
        finally:
            await browser.close()


async def test_no_modal_still_resolves_document_field():
    """Without a modal, resolution is unchanged (document-wide)."""
    aw = pytest.importorskip("playwright.async_api")
    async with aw.async_playwright() as p:
        launch_kwargs = {}
        exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
        if exe:
            launch_kwargs["executable_path"] = exe
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(
                '<form><div class="ant-form-item"><div class="ant-form-item-label">'
                '<label>Description</label></div><textarea data-testid="only" class="ant-input">'
                '</textarea></div></form>'
            )
            adapter = PlaywrightAdapter(page)
            ref = await adapter.find_input("Description")
            which = await page.eval_on_selector(ref, "e => e.getAttribute('data-testid')")
            assert which == "only"
        finally:
            await browser.close()
