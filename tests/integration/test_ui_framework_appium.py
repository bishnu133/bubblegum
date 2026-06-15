"""M4 real-device test: UI framework detection is wired into context.

Gated behind --appium. Confirms the adapter populates
``app_state["ui_framework"]`` from a live hierarchy (e.g. the Settings app →
native_android). Skips cleanly without a device.
"""

from __future__ import annotations

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.planner import context_request

pytestmark = [pytest.mark.appium, pytest.mark.bubblegum]

_KNOWN = {
    "jetpack_compose", "flutter", "react_native", "swiftui",
    "native_android", "native_ios",
}


@pytest.mark.asyncio
async def test_ui_framework_detected_on_device(bubblegum_mobile):
    adapter = AppiumAdapter(bubblegum_mobile.driver)
    ctx = await adapter.collect_context(context_request())

    uifw = ctx.app_state.get("ui_framework")
    assert isinstance(uifw, dict), "adapter should populate app_state['ui_framework']"
    assert uifw["framework"] in _KNOWN
    assert uifw["framework"] != "unknown"
    assert uifw["safe_metadata_only"] is True
