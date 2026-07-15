"""Expand/collapse the RIGHT accordion panel when a label is shared across sections.

A Rewards page carries a "Drink" collapse panel under BOTH a "Rewards Gamification"
and a "Bonus Gamification" heading (each collapsed by default). The generic
clickable path ties on the label "Drink" and picks the first in DOM order, so the
step meant for the Bonus panel re-clicks the Rewards one — expanding one appears to
collapse the other. ``_maybe_resolve_collapse`` pins the right header by its panel
label + section context and returns a stable, section-specific selector.

It is also idempotent: an "expand" step whose panel is already open is a no-op, so
it can never toggle an already-open panel shut.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk


def _panel(section_id_prefix: str, label: str, expanded: bool) -> str:
    active = " ant-collapse-item-active" if expanded else ""
    aria = "true" if expanded else "false"
    content_cls = "ant-collapse-content-active" if expanded else "ant-collapse-content-hidden"
    style = "" if expanded else "display:none"
    return (
        f"<div class='ant-collapse-item{active}'>"
        f"  <div class='ant-collapse-header' role='button' aria-expanded='{aria}' tabindex='0'>"
        f"    <div class='ant-collapse-expand-icon'><span aria-label='{'expanded' if expanded else 'collapsed'}'>#</span></div>"
        f"    <span class='ant-collapse-header-text'><div style='font-weight:bold'>{label}</div></span>"
        f"  </div>"
        f"  <div class='ant-collapse-content {content_cls}' style='{style}'>"
        f"    <div class='ant-collapse-content-box'>"
        f"      <input role='spinbutton' id='{section_id_prefix}_{label.lower()}_0_maxRange' placeholder='Position'>"
        f"    </div>"
        f"  </div>"
        f"</div>"
    )


# Two sections, each an <h4> heading followed by an Ant collapse with a (default
# open) Food panel and a (default collapsed) Drink panel. A tiny script gives the
# headers REAL toggle behaviour so the test exercises the same click the SDK issues.
_PAGE = (
    "<!doctype html><html><body>"
    "<div style='margin-bottom:40px'>"
    "  <h4>Rewards Gamification</h4>"
    "  <div class='ant-collapse'>"
    + _panel("normalRewards", "Food", expanded=True)
    + _panel("normalRewards", "Drink", expanded=False)
    + "  </div>"
    "</div>"
    "<div style='margin-bottom:40px'>"
    "  <h4>Bonus Gamification</h4>"
    "  <div class='ant-collapse'>"
    + _panel("bonusRewards", "Food", expanded=True)
    + _panel("bonusRewards", "Drink", expanded=False)
    + "  </div>"
    "</div>"
    "<script>"
    "document.querySelectorAll('.ant-collapse-header').forEach(function(h){"
    "  h.addEventListener('click', function(){"
    "    var open = h.getAttribute('aria-expanded') === 'true';"
    "    h.setAttribute('aria-expanded', open ? 'false' : 'true');"
    "    var item = h.closest('.ant-collapse-item');"
    "    item.classList.toggle('ant-collapse-item-active', !open);"
    "    var c = item.querySelector('.ant-collapse-content');"
    "    c.classList.toggle('ant-collapse-content-hidden', open);"
    "    c.classList.toggle('ant-collapse-content-active', !open);"
    "    c.style.display = open ? 'none' : 'block';"
    "  });"
    "});"
    "</script>"
    "</body></html>"
)


def _states(page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('.ant-collapse-header')).map("
        "h => ((h.querySelector('.ant-collapse-header-text')||{}).textContent||'').trim()"
        " + ':' + h.getAttribute('aria-expanded'))"
    )


@pytest.mark.playwright
def test_expand_targets_correct_panel_across_like_named_sections() -> None:
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

                # Expand the Rewards Gamification "Drink" panel.
                r1 = await sdk.act(
                    'Click on "Drink" button to expand Drink section',
                    channel="web", page=page,
                )
                after1 = await _states(page)

                # Expand the Bonus Gamification "Drink" panel — must NOT re-click the
                # Rewards one (which would collapse it).
                r2 = await sdk.act(
                    'Click on "Drink" button to expand Drink section in Bonus Gamification',
                    channel="web", page=page,
                )
                after2 = await _states(page)

                # An already-open panel: "expand Food" must be a no-op, not a toggle.
                r3 = await sdk.act(
                    'Click on "Food" button to expand Food section',
                    channel="web", page=page,
                )
                after3 = await _states(page)
                return (r1.status, r1.target.resolver_name, after1,
                        r2.status, r2.target.resolver_name, after2,
                        r3.status, r3.target.resolver_name, after3)
            finally:
                await browser.close()
        finally:
            await pw.stop()

    (s1, name1, a1, s2, name2, a2, s3, name3, a3) = asyncio.run(go())

    assert s1 == "passed" and name1 == "collapse_dom"
    # Only the Rewards Drink (index 1) opened; Bonus Drink (index 3) still closed.
    assert a1 == ["Food:true", "Drink:true", "Food:true", "Drink:false"]

    assert s2 == "passed" and name2 == "collapse_dom"
    # Now Bonus Drink is open too — and the Rewards Drink stayed open.
    assert a2 == ["Food:true", "Drink:true", "Food:true", "Drink:true"]

    # Idempotent expand: Food was already open, so nothing toggled shut.
    assert s3 == "passed" and name3 == "collapse_dom"
    assert a3 == ["Food:true", "Drink:true", "Food:true", "Drink:true"]
