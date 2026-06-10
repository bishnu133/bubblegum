"""Phase 22E-8: bubblegum_mobile fixture — live integration.

Gated by ``--appium`` AND requires capabilities, so it is skipped in normal
runs and in CI without a device. Run against a real Appium server + device:

    pytest --appium -m bubblegum \\
      --bubblegum-appium-url http://localhost:4723 \\
      --bubblegum-capabilities '{"platformName": "Android",
        "appium:deviceName": "emulator-5554",
        "appium:appPackage": "io.appium.android.apis",
        "appium:appActivity": ".ApiDemos",
        "appium:automationName": "UiAutomator2"}' \\
      tests/integration/test_phase22e8_mobile_fixture.py

It proves the fixture mirrors ``bubblegum_web``: NL ``act`` runs through the
mobile channel on a driver the fixture built from CLI options.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.appium, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_mobile_session_runs_nl_act(bubblegum_mobile):
    # The fixture handed us a ready BubblegumSession.mobile; the driver was
    # built from --bubblegum-appium-url + --bubblegum-capabilities.
    assert bubblegum_mobile.channel == "mobile"
    assert bubblegum_mobile.driver is not None

    # ApiDemos home screen: tap a known list item by its visible label.
    result = await bubblegum_mobile.act("Tap Animation")

    assert result.status in ("passed", "recovered"), result.error
    bubblegum_mobile.assert_all_passed()
