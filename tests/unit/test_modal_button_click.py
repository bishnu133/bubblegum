"""Clicking a button inside an open modal, not its twin behind the mask.

An Ant modal's footer often has an "Add"/"OK"/"Save" button whose label matches a
button on the page behind it. The page copy is covered by the modal mask
(`.ant-modal-wrap`), so clicking it hangs ("subtree intercepts pointer events").
The dialog-click pre-resolver must pin the button INSIDE the dialog — and it must
fire for the natural phrasing `Click on "Add" button`.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk


_PAGE = (
    "<!doctype html><html><body>"
    "<button type='button' id='add-basket-button' class='ant-btn ant-btn-primary'"
    " onclick='window.__basket=1'><span>Add</span></button>"
    "<div class='ant-modal-root'>"
    "  <div class='ant-modal-mask' style='position:fixed;inset:0;z-index:1000'></div>"
    "  <div tabindex='-1' class='ant-modal-wrap' style='position:fixed;inset:0;z-index:1000'>"
    "    <div role='dialog' aria-modal='true' class='ant-modal'"
    "         style='width:700px;position:relative;z-index:1001;margin:80px auto;background:#fff'>"
    "      <div class='ant-modal-content'>"
    "        <div class='ant-modal-header'><div class='ant-modal-title'>Add a Product</div></div>"
    "        <div class='ant-modal-body'>body</div>"
    "        <div class='ant-modal-footer'>"
    "          <button type='button' class='ant-btn' onclick='window.__cancel=1'><span>Cancel</span></button>"
    "          <button type='button' class='ant-btn ant-btn-primary' onclick='window.__modalAdd=1'><span>Add</span></button>"
    "        </div>"
    "      </div>"
    "    </div>"
    "  </div>"
    "</div></body></html>"
)


@pytest.mark.playwright
def test_click_add_targets_modal_button_not_masked_page_button() -> None:
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
                await page.set_content(_PAGE)
                result = await sdk.act('Click on "Add" button', channel="web", page=page)
                return (
                    result.status,
                    await page.evaluate("window.__modalAdd || 0"),
                    await page.evaluate("window.__basket || 0"),
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    status, modal_add, basket = asyncio.run(go())
    assert status == "passed"
    assert modal_add == 1        # the modal footer's Add button was clicked
    assert basket == 0           # NOT the same-named button behind the mask
