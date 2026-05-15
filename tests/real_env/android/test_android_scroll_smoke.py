from __future__ import annotations

import asyncio
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.mobile.scroll_discovery import execute_bounded_mobile_scroll_search
from bubblegum.core.schemas import ContextRequest
from tests.real_env.conftest import require_real_env_enabled


pytestmark = [
    pytest.mark.real_env,
    pytest.mark.android_emulator,
    pytest.mark.android_device,
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
        missing.append("BUBBLEGUM_ANDROID_APP (or BUBBLEGUM_ANDROID_PACKAGE + BUBBLEGUM_ANDROID_ACTIVITY)")

    if missing:
        pytest.skip("Android scroll smoke requires: " + ", ".join(missing))

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


def test_android_emulator_scroll_discovery_smoke_mvp() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()

    max_scrolls = int(os.getenv("BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS", "3"))
    target_text = os.getenv("BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT", "").strip()
    enable_scroll_action = os.getenv("BUBBLEGUM_ANDROID_ENABLE_SCROLL_ACTION", "").strip() == "1"

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
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Unable to start Android scroll smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))

        assert "scroll_discovery" in ui_context.app_state
        scroll_discovery = ui_context.app_state["scroll_discovery"]
        assert isinstance(scroll_discovery, dict)
        for key in (
            "scroll_needed",
            "status",
            "reason",
            "platform",
            "target_hint_type",
            "scroll_direction",
            "max_scrolls",
            "candidate_container_count",
            "evidence",
            "warnings",
            "safe_metadata_only",
        ):
            assert key in scroll_discovery

        for forbidden in (
            "hierarchy_xml",
            "screenshot",
            "screenshot_bytes",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
        ):
            assert forbidden not in scroll_discovery

        should_scroll = enable_scroll_action and bool(target_text)
        if not should_scroll:
            return

        action_result = execute_bounded_mobile_scroll_search(
            driver=driver,
            target_hint=target_text,
            plan={"max_scrolls": max_scrolls},
            explicit_opt_in=True,
        )

        assert action_result["action_attempted"] is True
        assert action_result["scroll_attempts"] <= max(1, min(max_scrolls, 10))

        if not action_result["target_found"]:
            pytest.fail(
                "BUBBLEGUM_ANDROID_ENABLE_SCROLL_ACTION=1 with BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT set "
                "explicitly requested bounded scroll search, but the target was not found."
            )
    finally:
        try:
            driver.quit()
        except Exception:
            pass
