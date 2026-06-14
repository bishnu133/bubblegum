"""M1 real-device test: mobile gesture vocabulary via Appium.

Gated behind --appium and a connected device/emulator. Because a meaningful
long-press needs a specific app + element, the target is supplied externally
(env vars), mirroring the real-env smoke harness — the test skips cleanly when
they are unset, so it never fails a CI run that lacks a device.

Env vars:
  BUBBLEGUM_GESTURE_TARGET    NL label to long-press, e.g. "the first message"
  BUBBLEGUM_GESTURE_MENU_TEXT optional text expected to appear after the
                              long-press (e.g. a context-menu item like "Delete")
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.appium, pytest.mark.bubblegum]


@pytest.mark.asyncio
async def test_long_press_opens_context_menu(bubblegum_mobile):
    target = os.environ.get("BUBBLEGUM_GESTURE_TARGET")
    if not target:
        pytest.skip("set BUBBLEGUM_GESTURE_TARGET to the element to long-press")

    s = bubblegum_mobile
    result = await s.act(f"Long press {target}")
    assert result.status in ("passed", "recovered"), result.error

    menu_text = os.environ.get("BUBBLEGUM_GESTURE_MENU_TEXT")
    if menu_text:
        verify = await s.verify(f"{menu_text} is visible")
        assert verify.status == "passed", verify.error
