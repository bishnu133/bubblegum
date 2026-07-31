"""Feature: a last-resort fallback selector clicks the element when every
natural + AI approach fails to identify it.

The step names an element that name/text/role grounding and the DOM fallbacks
cannot resolve (a bare icon-only control with no accessible name and a phrase
that matches nothing). With ``fallback_selector`` supplied, the engine uses it
as a safety net so the step still passes — and the result is flagged as a
fallback (not a self-heal).

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

_PAGE = """
<!doctype html><html><body>
  <!-- No accessible name, no text — natural grounding can't identify it. -->
  <div id="gizmo" data-testid="gizmo" style="width:40px;height:40px;background:#ccc"
       onclick="window.__clicked=(window.__clicked||0)+1"></div>
</body></html>
"""


async def _run(instruction, options):
    aw = pytest.importorskip("playwright.async_api")
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_PAGE)
            res = await act(instruction, channel="web", page=page, **options)
            clicked = await page.evaluate("window.__clicked || 0")
            return res, clicked
        finally:
            await browser.close()


async def test_fallback_selector_clicks_when_natural_resolution_fails():
    res, clicked = await _run(
        'Click the "Totally Unresolvable Gizmo Zzz" control',
        {"fallback_selector": '[data-testid="gizmo"]'},
    )
    assert res.status == "passed"
    assert clicked == 1
    # Flagged as a fallback, not a self-heal.
    assert res.target is not None
    assert res.target.resolver_name == "fallback_selector"
    assert res.target.metadata.get("fallback_selector_used") is True


async def test_without_fallback_the_same_step_fails():
    """Baseline: no fallback selector → the unresolvable step fails, nothing clicked."""
    res, clicked = await _run('Click the "Totally Unresolvable Gizmo Zzz" control', {})
    assert res.status == "failed"
    assert clicked == 0
