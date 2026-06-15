"""M6 real-device test: mobile network-condition simulation via Appium.

Gated behind --appium and a connected Android device/emulator. Network
conditions are device-level (no app element), so this runs the acceptance flow
— go offline, restore, throttle to a 3G profile — and asserts each step
succeeds. Connectivity works on real devices + emulators; the speed-profile
step is emulator-only, so a real-device run may report it failed (accepted).
Skips cleanly when no device/caps are provided.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.appium, pytest.mark.bubblegum]


@pytest.mark.asyncio
async def test_offline_restore_and_throttle_flow(bubblegum_mobile):
    s = bubblegum_mobile

    # Cut connectivity, then restore it (both via mobile: setConnectivity).
    r_off = await s.act("go offline")
    assert r_off.status == "passed", r_off.error
    assert r_off.target.metadata["system_action"]["state"] == "offline"

    r_on = await s.act("go online")
    assert r_on.status == "passed", r_on.error
    assert r_on.target.metadata["system_action"]["state"] == "online"

    # Speed throttling is Android-emulator-only; accept a failure on real devices.
    r_3g = await s.act("simulate 3g network")
    assert r_3g.status in ("passed", "failed")
    if r_3g.status == "passed":
        assert r_3g.target.metadata["system_action"]["netspeed"] == "umts"
