"""X3: coordinate-based vision clicking — hydrator fallback + adapter execution.

No browser/device: a fake Playwright page and a fake Appium driver record the
coordinate they were asked to click/tap.
"""

from __future__ import annotations

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.grounding.hydrator import VisualRefHydrator
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget, StepIntent


def _intent(channel="web", action_type="click", *, fallback=True, **ctx):
    intent = StepIntent(
        instruction="Tap the player",
        channel=channel,
        platform="web" if channel == "web" else "android",
        action_type=action_type,
    )
    if fallback:
        intent.context["coordinate_click_fallback"] = True
    intent.context.update(ctx)
    return intent


def _vision_target(bbox=(10, 20, 110, 70), **md):
    meta = {"bbox": list(bbox)}
    meta.update(md)
    return ResolvedTarget(
        ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata=meta
    )


# ---------------------------------------------------------------------------
# Hydrator coordinate fallback
# ---------------------------------------------------------------------------

def test_fallback_hydrates_to_point_ref_when_no_element_mapping():
    # No text/role/label → deterministic mapping fails; bbox + opt-in → point ref.
    target = _vision_target()
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.reason == "hydrated_coordinate_fallback"
    assert out.target.ref == "point://60,45"
    assert out.target.metadata["hydration_strategy"] == "coordinate"
    assert out.target.metadata["coordinate_point"] == [60, 45]
    assert out.target.metadata["hydrated_from_ref"] == "vision://target/0"


def test_fallback_disabled_by_default_keeps_failure():
    target = _vision_target()
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web", fallback=False))
    assert out.status == "not_hydrated"


def test_deterministic_mapping_wins_over_coordinate():
    # A label is present → deterministic text mapping should win; no point ref.
    target = _vision_target(label="Login")
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target.ref == 'text="Login"'
    assert out.target.metadata["hydration_strategy"] == "text"


def test_fallback_only_for_click_tap_actions():
    target = _vision_target()
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web", action_type="type"))
    assert out.status == "not_hydrated"


def test_fallback_requires_usable_bbox():
    target = _vision_target(bbox=(10, 20, 10, 70))  # zero width
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "not_hydrated"


def test_fallback_works_on_mobile_without_hierarchy():
    target = _vision_target()
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("mobile", action_type="tap"))
    assert out.status == "hydrated"
    assert out.target.ref == "point://60,45"
    assert out.diagnostics["channel"] == "mobile"


def test_fallback_for_ocr_ref():
    target = ResolvedTarget(
        ref="ocr://block/0", confidence=0.7, resolver_name="ocr", metadata={"bbox": [0, 0, 40, 40]}
    )
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target.ref == "point://20,20"
    assert out.diagnostics["source"] == "ocr"


# ---------------------------------------------------------------------------
# Web adapter coordinate execution
# ---------------------------------------------------------------------------

class _FakeMouse:
    def __init__(self):
        self.clicks: list[tuple[int, int]] = []

    async def click(self, x, y):
        self.clicks.append((x, y))


class _FakePage:
    def __init__(self):
        self.mouse = _FakeMouse()
        self.url = "https://example.test"


def _plan(action_type="click"):
    return ActionPlan(action_type=action_type, target_hint="x", options=ExecutionOptions())


@pytest.mark.asyncio
async def test_web_adapter_clicks_coordinate():
    page = _FakePage()
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref="point://60,45", confidence=0.8, resolver_name="vision_model", metadata={})
    result = await adapter.execute(_plan("click"), target)
    assert result.success
    assert page.mouse.clicks == [(60, 45)]
    assert target.metadata["coordinate_click"] is True
    assert target.metadata["coordinate_point"] == [60, 45]


@pytest.mark.asyncio
async def test_web_adapter_rejects_type_at_coordinate():
    page = _FakePage()
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref="point://60,45", confidence=0.8, resolver_name="vision_model", metadata={})
    result = await adapter.execute(_plan("type"), target)
    assert not result.success
    assert "coordinate-clickable" in result.error
    assert page.mouse.clicks == []


# ---------------------------------------------------------------------------
# Mobile adapter coordinate execution
# ---------------------------------------------------------------------------

class _FakeDriver:
    def __init__(self):
        self.taps: list[list[tuple[int, int]]] = []

    def tap(self, positions, duration=None):
        self.taps.append(positions)


@pytest.mark.asyncio
async def test_mobile_adapter_taps_coordinate():
    driver = _FakeDriver()
    adapter = AppiumAdapter(driver)
    target = ResolvedTarget(ref="point://12,34", confidence=0.8, resolver_name="vision_model", metadata={})
    result = await adapter.execute(_plan("tap"), target)
    assert result.success
    assert driver.taps == [[(12, 34)]]
    assert target.metadata["coordinate_click"] is True
    assert target.metadata["coordinate_adapter"] == "appium"


@pytest.mark.asyncio
async def test_mobile_adapter_rejects_malformed_point():
    driver = _FakeDriver()
    adapter = AppiumAdapter(driver)
    # An adapter should never receive this, but fail closed if it does.
    target = ResolvedTarget(ref="point://bad", confidence=0.8, resolver_name="vision_model", metadata={})
    result = await adapter.execute(_plan("tap"), target)
    assert not result.success
    assert driver.taps == []
