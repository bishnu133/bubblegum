"""
tests/integration/test_phase4_appium.py
========================================
Phase 4 Appium integration tests.

These tests require:
  - A running Appium 2.x/3.x server (localhost:4723)
  - A connected Android emulator with ApiDemos app installed
  - The --appium flag: pytest tests/integration/test_phase4_appium.py --appium

The tests verify two key behaviours:
  1. Run 1  — AppiumHierarchyResolver resolves an element on first execution;
              result written to SQLite.
  2. Run 2  — MemoryCacheResolver wins on replay; no AI calls made.

Configure the target app by setting these environment variables:
  APPIUM_APP_PACKAGE   (default: io.appium.android.apis)
  APPIUM_APP_ACTIVITY  (default: .ApiDemos)
  APPIUM_DEVICE_NAME   (default: emulator-5554)
  APPIUM_PLATFORM_VER  (default: 16)
  APPIUM_URL           (default: http://localhost:4723)
"""

from __future__ import annotations

import os
import time
import pytest


pytestmark = pytest.mark.appium


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _back_to_home(driver, app_package: str, app_activity: str) -> None:
    """
    Navigate back to the ApiDemos home screen so the screen signature
    matches what was cached in Run 1.

    Uses driver.start_activity() to re-launch the main activity without
    resetting app state, which is faster than a full session restart.
    """
    try:
        driver.start_activity(app_package, app_activity)
        time.sleep(1)
    except Exception:
        # Fallback: press back until we reach the home screen
        for _ in range(5):
            try:
                driver.back()
                time.sleep(0.3)
            except Exception:
                break


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def appium_driver():
    """
    Create and yield a real Appium WebDriver session.
    Uses no_reset=False to ensure the app is launched fresh.
    Quits the session after all tests in this module complete.
    """
    try:
        import appium.webdriver as appium_webdriver
    except ImportError:
        pytest.skip("appium-python-client not installed — run: pip install Appium-Python-Client")

    # Support Appium Python Client v3.x, v4.x, and v5.x import paths
    UiAutomator2Options = None
    for module_path, class_name in [
        ("appium.options.android", "UiAutomator2Options"),  # v5.x
        ("appium.options",         "UiAutomator2Options"),  # v3.x / v4.x
    ]:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            UiAutomator2Options = getattr(mod, class_name)
            break
        except (ImportError, AttributeError):
            continue

    if UiAutomator2Options is None:
        pytest.skip(
            "Could not import UiAutomator2Options — run: pip install --upgrade Appium-Python-Client"
        )

    options = UiAutomator2Options()
    options.platform_name          = "Android"
    options.device_name            = os.getenv("APPIUM_DEVICE_NAME", "emulator-5554")
    options.app_package            = os.getenv("APPIUM_APP_PACKAGE",  "io.appium.android.apis")
    options.app_activity           = os.getenv("APPIUM_APP_ACTIVITY", ".ApiDemos")
    options.platform_version       = os.getenv("APPIUM_PLATFORM_VER", "16")
    options.no_reset               = False
    options.auto_grant_permissions = True

    appium_url = os.getenv("APPIUM_URL", "http://localhost:4723")

    try:
        driver = appium_webdriver.Remote(appium_url, options=options)
    except Exception as exc:
        pytest.skip(f"Cannot connect to Appium server at {appium_url}: {exc}")

    # Give the app time to fully load
    time.sleep(2)

    yield driver
    driver.quit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.appium
def test_appium_hierarchy_resolver_wins_on_first_run(appium_driver):
    """
    Run 1: AppiumHierarchyResolver resolves 'Animation' on the ApiDemos home
    screen. The screen_signature + step_hash → ref mapping is written to SQLite.
    """
    import asyncio
    from bubblegum.core import sdk

    app_package  = os.getenv("APPIUM_APP_PACKAGE",  "io.appium.android.apis")
    app_activity = os.getenv("APPIUM_APP_ACTIVITY", ".ApiDemos")

    # Ensure we are on the home screen before Run 1
    _back_to_home(appium_driver, app_package, app_activity)

    instruction = "Tap Animation"

    result = asyncio.get_event_loop().run_until_complete(
        sdk.act(
            instruction,
            channel="mobile",
            driver=appium_driver,
            platform="android",
        )
    )

    assert result.status in ("passed", "recovered"), (
        f"Expected passed or recovered, got {result.status}.\n"
        f"Error: {result.error}\n"
        f"Traces: {result.traces}"
    )
    assert result.target is not None, "Expected a resolved target"
    assert result.confidence > 0.0,   "Expected non-zero confidence"

    winning_resolver = result.target.resolver_name
    assert winning_resolver == "appium_hierarchy", (
        f"Expected appium_hierarchy to win on first run, got: {winning_resolver}"
    )

    print(f"\n✅ Run 1: resolver={winning_resolver}  confidence={result.confidence:.2f}  "
          f"ref={result.target.ref}")


@pytest.mark.appium
def test_memory_cache_resolver_wins_on_second_run(appium_driver):
    """
    Run 2: MemoryCacheResolver wins on replay using the SQLite-cached mapping.

    Navigates back to the ApiDemos home screen first so the screen_signature
    matches what was stored in Run 1. No AI calls are made.
    """
    import asyncio
    from bubblegum.core import sdk

    app_package  = os.getenv("APPIUM_APP_PACKAGE",  "io.appium.android.apis")
    app_activity = os.getenv("APPIUM_APP_ACTIVITY", ".ApiDemos")

    # Navigate back to home screen so screen_signature matches the cached value
    _back_to_home(appium_driver, app_package, app_activity)

    instruction = "Tap Animation"

    result = asyncio.get_event_loop().run_until_complete(
        sdk.act(
            instruction,
            channel="mobile",
            driver=appium_driver,
            platform="android",
        )
    )

    assert result.status in ("passed", "recovered"), (
        f"Expected passed or recovered, got {result.status}.\n"
        f"Error: {result.error}\n"
        f"Traces: {result.traces}"
    )

    winning_resolver = result.target.resolver_name if result.target else "none"
    assert winning_resolver == "memory_cache", (
        f"Expected memory_cache to win on second run (replay), got: {winning_resolver}.\n"
        "Ensure Run 1 completed successfully and .bubblegum/memory.db exists."
    )

    print(f"\n✅ Run 2: resolver={winning_resolver}  (replayed from SQLite — no AI call)")