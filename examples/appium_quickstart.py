"""Minimal Appium + Bubblegum template.

Requirements:
  pip install -e ".[mobile]"
  # package users: pip install "bubblegum-ai[mobile]"
  # plus: running Appium server and connected emulator/device
"""

from __future__ import annotations

import asyncio

from bubblegum import act, verify


def build_driver():
    """Create an Appium driver (template values; replace as needed)."""
    from appium import webdriver

    capabilities = {
        "platformName": "Android",
        "appium:deviceName": "emulator-5554",
        "appium:automationName": "UiAutomator2",
        # Example app placeholders:
        "appium:appPackage": "io.appium.android.apis",
        "appium:appActivity": ".ApiDemos",
        "appium:noReset": False,
    }

    # Default local Appium server URL; update for your environment.
    return webdriver.Remote("http://localhost:4723", capabilities)


async def main() -> None:
    driver = build_driver()
    try:
        tapped = await act("Tap Animation", channel="mobile", platform="android", driver=driver)
        print("act status:", tapped.status)

        checked = await verify(
            "Animation screen",
            channel="mobile",
            platform="android",
            driver=driver,
            assertion_type="text_visible",
            expected_value="Animation",
        )
        print("verify status:", checked.status)
    finally:
        driver.quit()


if __name__ == "__main__":
    asyncio.run(main())
