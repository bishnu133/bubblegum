from __future__ import annotations

import asyncio
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest
from tests.real_env.conftest import require_real_env_enabled


pytestmark = [
    pytest.mark.real_env,
    pytest.mark.android_emulator,
    pytest.mark.android_device,
    pytest.mark.hybrid_webview,
    pytest.mark.slow,
]


def _required_android_env() -> tuple[str, dict[str, str], bool]:
    require_real_env_enabled()

    values = {
        "BUBBLEGUM_APPIUM_SERVER_URL": os.getenv("BUBBLEGUM_APPIUM_SERVER_URL", "").strip(),
        "BUBBLEGUM_ANDROID_DEVICE_NAME": os.getenv("BUBBLEGUM_ANDROID_DEVICE_NAME", "").strip(),
        "BUBBLEGUM_ANDROID_APP": os.getenv("BUBBLEGUM_ANDROID_APP", "").strip(),
        "BUBBLEGUM_ANDROID_PACKAGE": os.getenv("BUBBLEGUM_ANDROID_PACKAGE", "").strip(),
        "BUBBLEGUM_ANDROID_ACTIVITY": os.getenv("BUBBLEGUM_ANDROID_ACTIVITY", "").strip(),
    }

    missing: list[str] = []
    if not values["BUBBLEGUM_APPIUM_SERVER_URL"]:
        missing.append("BUBBLEGUM_APPIUM_SERVER_URL")
    if not values["BUBBLEGUM_ANDROID_DEVICE_NAME"]:
        missing.append("BUBBLEGUM_ANDROID_DEVICE_NAME")

    has_app = bool(values["BUBBLEGUM_ANDROID_APP"])
    has_pkg_activity = bool(values["BUBBLEGUM_ANDROID_PACKAGE"] and values["BUBBLEGUM_ANDROID_ACTIVITY"])
    if not has_app and not has_pkg_activity:
        missing.append(
            "BUBBLEGUM_ANDROID_APP (or BUBBLEGUM_ANDROID_PACKAGE + BUBBLEGUM_ANDROID_ACTIVITY)"
        )

    if missing:
        pytest.skip(
            "Android emulator smoke requires: " + ", ".join(missing)
        )

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


def test_android_emulator_smoke_collect_context_mvp() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()

    options = options_module.UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = values["BUBBLEGUM_ANDROID_DEVICE_NAME"]

    if has_app:
        options.app = values["BUBBLEGUM_ANDROID_APP"]
    else:
        options.app_package = values["BUBBLEGUM_ANDROID_PACKAGE"]
        options.app_activity = values["BUBBLEGUM_ANDROID_ACTIVITY"]

    options.automation_name = "UiAutomator2"

    try:
        driver = appium_webdriver.Remote(appium_url, options=options)
    except Exception as exc:  # pragma: no cover - runtime-dependent skip path
        pytest.skip(f"Unable to start Android emulator smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(
            adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
        )

        assert adapter.channel == "mobile"
        assert ui_context.hierarchy_xml is None or isinstance(ui_context.hierarchy_xml, str)

        app_state = ui_context.app_state
        for key in (
            "context_inventory",
            "framework_detection",
            "webview_switch_diagnostics",
            "webview_switch_guardrails",
        ):
            assert key in app_state

        target_text = os.getenv("BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT", "").strip()
        if target_text:
            appiumby = pytest.importorskip("appium.webdriver.common.appiumby")
            target_xpath = f"//*[@text={target_text!r} or @content-desc={target_text!r}]"
            try:
                matches = driver.find_elements(appiumby.AppiumBy.XPATH, target_xpath)
            except Exception as exc:
                pytest.fail(f"Target lookup failed for BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT: {exc}")

            if not matches:
                pytest.fail(
                    "BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT was provided, but no matching native element was found."
                )

            matches[0].click()
    finally:
        try:
            driver.quit()
        except Exception:
            pass
