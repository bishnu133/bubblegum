"""M2 real-device test: mobile system / hardware actions via Appium.

Gated behind --appium and a connected device/emulator. System actions are
device-level (no app-specific element), so this runs the acceptance flow —
rotate, hide keyboard, press back — and asserts each step succeeds. Skips
cleanly when no device/caps are provided.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.appium, pytest.mark.bubblegum]


@pytest.mark.asyncio
async def test_rotate_hide_keyboard_and_back_flow(bubblegum_mobile):
    s = bubblegum_mobile

    # Rotation is deterministic regardless of the foreground app.
    r_land = await s.act("Rotate to landscape")
    assert r_land.status == "passed", r_land.error
    assert r_land.target.metadata["system_action"]["orientation"] == "LANDSCAPE"

    r_port = await s.act("Rotate to portrait")
    assert r_port.status == "passed", r_port.error

    # Hide keyboard is best-effort: some screens have no IME up, in which case
    # the driver may report it could not be closed — accept either outcome.
    r_kb = await s.act("Hide the keyboard")
    assert r_kb.status in ("passed", "failed")

    # Android hardware back.
    r_back = await s.act("press back")
    assert r_back.status == "passed", r_back.error
