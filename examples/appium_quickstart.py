"""Minimal Appium + Bubblegum template.

Requirements:
  pip install -e ".[mobile]"
  # package users: pip install "bubblegum-ai[mobile]"
  # plus: running Appium server and connected emulator/device
"""

from __future__ import annotations

import asyncio

from bubblegum import act, verify


APPIUM_INSTALL_HINT = """Appium Python client is not installed.
Install mobile dependencies with one of:
  pip install -e ".[mobile]"
  pip install "bubblegum-ai[mobile]"
"""

APPIUM_SESSION_HINT = """Could not create an Appium session.
Checklist:
  1) Start Appium server (default URL: http://localhost:4723)
  2) Connect/start an emulator or physical device
  3) Update capabilities for your local app/device
"""


def build_driver():
    """Create an Appium driver (template values; replace as needed)."""
    try:
        from appium import webdriver
    except ModuleNotFoundError:
        print(APPIUM_INSTALL_HINT)
        return None

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
    try:
        return webdriver.Remote("http://localhost:4723", capabilities)
    except Exception as exc:
        print(f"Appium session startup failed: {exc}")
        print(APPIUM_SESSION_HINT)
        return None


async def main() -> None:
    driver = build_driver()
    if driver is None:
        return

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
    except Exception as exc:
        print(f"Appium quickstart failed during execution: {exc}")
        print(APPIUM_SESSION_HINT)
    finally:
        driver.quit()


if __name__ == "__main__":
    asyncio.run(main())
