"""Feature: date/time picker entry is robust to a dropped first commit.

Reproduces the headless-only failure where "Enter 06:00 into Start time" worked
locally (headed) but silently entered nothing on CI (headless): the picker's
first commit can be lost to a race with the widget's open/close animation, so
the field ends up empty. The engine now activates the field, types the value
with real keystrokes, presses Enter, then VERIFIES the value stuck and retries
once if it didn't.

The test element models that flake: the FIRST Enter drops the value (as a lost
commit would); a second attempt sticks. So this passes on the verify+retry path
and fails on the old single-shot path.

Runs against a real (headless) browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

# A blocking modal holding a time RangePicker whose first commit is dropped —
# the first Enter clears the field (a lost headless commit); the retry sticks.
_PAGE = """
<!doctype html><html><body style="font-family:Helvetica">
  <div class="ant-modal-root"><div class="ant-modal-mask"></div>
    <div class="ant-modal-wrap"><div role="dialog" aria-modal="true" class="ant-modal" style="z-index:1000">
      <div class="ant-modal-content">
        <div class="ant-modal-header">Add Sessions</div>
        <div class="ant-modal-body"><form>
          <div class="ant-form-item"><div class="ant-form-item-label"><label>Session Time (24 hour)</label></div>
            <div class="ant-picker ant-picker-range">
              <input id="tstart" date-range="start" placeholder="Start time" autocomplete="off">
              <input id="tend" date-range="end" placeholder="End time" autocomplete="off">
            </div></div>
        </form></div>
        <div class="ant-modal-footer"><button type="button">Add</button></div>
      </div></div></div></div>
  <script>
    // Simulate a flaky commit: the FIRST Enter each field receives drops the
    // typed value (as a lost commit would in headless); later attempts stick.
    for (const id of ['tstart','tend']) {
      const inp = document.getElementById(id);
      let enters = 0;
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { enters++; if (enters === 1) inp.value = ''; }
      });
    }
  </script>
</body></html>
"""


async def _page(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)   # headless by default
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(_PAGE)
    return browser, page


async def test_start_time_survives_dropped_first_commit():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act('Enter "06:00" into Session Start time in dialog',
                            channel="web", page=page)
            assert res.status in ("passed", "recovered"), res.error and res.error.message
            val = await page.eval_on_selector("#tstart", "e => e.value")
            assert val == "06:00", f"start time not committed after retry (got {val!r})"
        finally:
            await browser.close()


async def test_end_time_survives_dropped_first_commit():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act('Enter "08:00" into Session End time in dialog',
                            channel="web", page=page)
            assert res.status in ("passed", "recovered"), res.error and res.error.message
            val = await page.eval_on_selector("#tend", "e => e.value")
            assert val == "08:00", f"end time not committed after retry (got {val!r})"
        finally:
            await browser.close()
