"""Section/column disambiguation for look-alike Rewards-page fields.

Two failures this covers, both from identically-labelled controls that only the
section/column context tells apart:

1. **Number inputs sharing a placeholder.** A "Stamp Position" field (an Ant
   range input whose visible label is a bare ``<span>`` and whose only accessible
   name is the placeholder "Position") exists in both a Food and a Drink panel.
   The field has no ``<label>``, so it looked "unique" to the a11y snapshot and a
   "Drink Stamp Position" step landed in the Food field. The input finder now
   folds the placeholder into the collision test, flags the field ``sectioned``,
   and the pre-resolver pins the right one by id/section.

2. **Dropdowns under a shared column-header row.** "Stamp Position" and
   "Bonus Type" label two side-by-side selects via one header row, so the finder
   used to grab the whole row and both columns tied — "Bonus Type" resolved to the
   Stamp Position select. A geometry-based column heading now labels each select
   by the header cell above it.
"""
from __future__ import annotations

import asyncio

import pytest

import bubblegum.core.sdk as sdk
import bubblegum.adapters.web.playwright.adapter as adapter_mod


def _num_panel(prefix: str, label: str) -> str:
    # A collapse panel with a "Stamp Position" range input (placeholder Position,
    # like Ant) and a "Healthpoints" input — both nameless, ids encode food/drink.
    return (
        f"<div class='ant-collapse-item ant-collapse-item-active'>"
        f"  <div class='ant-collapse-header' role='button' aria-expanded='true'>"
        f"    <span class='ant-collapse-header-text'><div>{label}</div></span></div>"
        f"  <div class='ant-collapse-content ant-collapse-content-active'>"
        f"    <div class='ant-collapse-content-box'>"
        f"      <div style='padding-bottom:8px'><span>Stamp Position</span></div>"
        f"      <input role='spinbutton' id='{prefix}_{label.lower()}_0_minRange'>"
        f"      <input role='spinbutton' id='{prefix}_{label.lower()}_0_maxRange' placeholder='Position'>"
        f"      <div style='padding-bottom:8px'><span>Healthpoints</span></div>"
        f"      <input role='spinbutton' id='{prefix}_{label.lower()}_0_healthPoints'>"
        f"    </div>"
        f"  </div>"
        f"</div>"
    )


_NUM_PAGE = (
    "<!doctype html><html><body>"
    "<div style='margin-bottom:40px'><h4>Rewards Gamification</h4>"
    "  <div class='ant-collapse'>"
    + _num_panel("normalRewards", "Food")
    + _num_panel("normalRewards", "Drink")
    + "  </div></div>"
    "</body></html>"
)


@pytest.mark.playwright
def test_drink_stamp_position_number_lands_in_drink_not_food() -> None:
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
                await page.set_content(_NUM_PAGE)
                await sdk.act('Enter "1" into Food Stamp Position', channel="web", page=page)
                r = await sdk.act('Enter "2" into Rewards Drink Stamp Position', channel="web", page=page)
                vals = await page.evaluate(
                    "() => ({food: document.getElementById('normalRewards_food_0_maxRange').value,"
                    " drink: document.getElementById('normalRewards_drink_0_maxRange').value})"
                )
                return r.status, vals
            finally:
                await browser.close()
        finally:
            await pw.stop()

    status, vals = asyncio.run(go())
    assert status == "passed"
    # The Drink value must NOT overwrite the Food field.
    assert vals == {"food": "1", "drink": "2"}


# Two side-by-side selects under ONE header row of column labels.
_DD_PAGE = (
    "<!doctype html><html><body>"
    "<div style='margin-bottom:40px'><h4>Bonus Gamification</h4>"
    "  <div style='display:flex;margin-bottom:8px'>"
    "    <span style='display:inline-block;width:155px;margin-right:16px'>Stamp Position</span>"
    "    <span style='display:inline-block;width:362px'>Bonus Type</span>"
    "  </div>"
    "  <div style='margin-bottom:16px'><div style='display:flex'>"
    "    <div class='ant-form-item' style='width:155px;margin-right:16px'>"
    "      <div class='ant-select ant-select-multiple' style='width:155px'><div class='ant-select-selector'>"
    "        <span class='ant-select-selection-search'><input id='bonusRewards_food_0_stampPosition'></span>"
    "        <span class='ant-select-selection-placeholder'>Select stamp positions</span></div></div></div>"
    "    <div class='ant-form-item' style='width:362px'>"
    "      <div class='ant-select ant-select-single' style='width:362px'><div class='ant-select-selector'>"
    "        <span class='ant-select-selection-search'><input id='bonusRewards_food_0_basketName'></span></div></div></div>"
    "  </div></div>"
    "</div></body></html>"
)


@pytest.mark.playwright
def test_bonus_type_dropdown_resolves_to_its_own_column() -> None:
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
                await page.set_content(_DD_PAGE)

                async def resolve(phrase):
                    res = await page.evaluate(
                        adapter_mod._FIND_SELECT_TRIGGER_JS, {"phrase": phrase, "value": ""}
                    )
                    return await page.eval_on_selector(
                        res["selector"],
                        "e => { const i = e.querySelector('[id]'); return i ? i.id : e.id; }",
                    )

                return await resolve("Stamp Position"), await resolve("Bonus Type")
            finally:
                await browser.close()
        finally:
            await pw.stop()

    stamp, bonus = asyncio.run(go())
    assert stamp == "bonusRewards_food_0_stampPosition"
    # "Bonus Type" must pick its OWN column (basketName), not the Stamp Position one.
    assert bonus == "bonusRewards_food_0_basketName"


def _bonus_panel(label: str) -> str:
    # A collapse panel whose header names it (Food/Drink), with a shared column
    # header row ("Stamp Position" | "Bonus Type") over two selects. The selects'
    # ids carry food/drink but NOT "bonus"/"type" — so only the panel header +
    # column header identify the "Bonus Type" select in the named panel.
    return (
        f"<div class='ant-collapse-item ant-collapse-item-active'>"
        f"  <div class='ant-collapse-header' role='button' aria-expanded='true'>"
        f"    <span class='ant-collapse-header-text'><div>{label}</div></span></div>"
        f"  <div class='ant-collapse-content ant-collapse-content-active'>"
        f"   <div class='ant-collapse-content-box'>"
        f"    <div style='display:flex;margin-bottom:8px'>"
        f"      <span style='display:inline-block;width:155px;margin-right:16px'>Stamp Position</span>"
        f"      <span style='display:inline-block;width:362px'>Bonus Type</span></div>"
        f"    <div style='display:flex'>"
        f"      <div class='ant-form-item' style='width:155px;margin-right:16px'>"
        f"        <div class='ant-select ant-select-multiple' style='width:155px'><div class='ant-select-selector'>"
        f"          <span class='ant-select-selection-search'><input id='bonusRewards_{label.lower()}_0_stampPosition'></span></div></div></div>"
        f"      <div class='ant-form-item' style='width:362px'>"
        f"        <div class='ant-select ant-select-single' style='width:362px'><div class='ant-select-selector'>"
        f"          <span class='ant-select-selection-search'><input id='bonusRewards_{label.lower()}_0_basketName'></span></div></div></div>"
        f"    </div>"
        f"   </div></div>"
        f"</div>"
    )


_TWO_PANEL_DD_PAGE = (
    "<!doctype html><html><body>"
    "<div style='margin-bottom:40px'><h4>Bonus Gamification</h4>"
    "  <div class='ant-collapse'>"
    + _bonus_panel("Food")
    + _bonus_panel("Drink")
    + "  </div></div>"
    "</body></html>"
)


@pytest.mark.playwright
def test_named_panel_qualifier_picks_the_right_panel_dropdown() -> None:
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
                await page.set_content(_TWO_PANEL_DD_PAGE)

                async def resolve(phrase):
                    res = await page.evaluate(
                        adapter_mod._FIND_SELECT_TRIGGER_JS, {"phrase": phrase, "value": ""}
                    )
                    return await page.eval_on_selector(
                        res["selector"],
                        "e => { const i = e.querySelector('[id]'); return i ? i.id : e.id; }",
                    )

                return (
                    await resolve("Drink Bonus Type"),
                    await resolve("Drink Stamp Position"),
                    await resolve("Food Bonus Type"),
                )
            finally:
                await browser.close()
        finally:
            await pw.stop()

    drink_bonus, drink_stamp, food_bonus = asyncio.run(go())
    # Each qualifier lands in its own panel + column, despite ids that carry no
    # "bonus"/"type" and column headers shared across both panels.
    assert drink_bonus == "bonusRewards_drink_0_basketName"
    assert drink_stamp == "bonusRewards_drink_0_stampPosition"
    assert food_bonus == "bonusRewards_food_0_basketName"
