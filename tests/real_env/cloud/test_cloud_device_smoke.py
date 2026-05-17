from __future__ import annotations

import asyncio
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest
from tests.real_env.cloud.harness import build_cloud_harness_config
from tests.real_env.conftest import require_real_env_enabled


pytestmark = [
    pytest.mark.real_env,
    pytest.mark.cloud_device,
    pytest.mark.hybrid_webview,
    pytest.mark.system_dialog,
    pytest.mark.slow,
]


def _required_cloud_env() -> tuple[str, str, dict[str, str], bool, bool, bool]:
    require_real_env_enabled()

    if os.getenv("BUBBLEGUM_CLOUD_DEVICE", "").strip() != "1":
        pytest.skip("Cloud device smoke harness is disabled. Set BUBBLEGUM_CLOUD_DEVICE=1 to opt in.")

    values = {
        "BUBBLEGUM_CLOUD_USERNAME": os.getenv("BUBBLEGUM_CLOUD_USERNAME", "").strip(),
        "BUBBLEGUM_CLOUD_ACCESS_KEY": os.getenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "").strip(),
        "BUBBLEGUM_CLOUD_PLATFORM": os.getenv("BUBBLEGUM_CLOUD_PLATFORM", "").strip().lower(),
        "BUBBLEGUM_CLOUD_DEVICE_NAME": os.getenv("BUBBLEGUM_CLOUD_DEVICE_NAME", "").strip(),
        "BUBBLEGUM_CLOUD_APP": os.getenv("BUBBLEGUM_CLOUD_APP", "").strip(),
        "BUBBLEGUM_CLOUD_APP_ID": os.getenv("BUBBLEGUM_CLOUD_APP_ID", "").strip(),
        "BUBBLEGUM_CLOUD_ANDROID_PACKAGE": os.getenv("BUBBLEGUM_CLOUD_ANDROID_PACKAGE", "").strip(),
        "BUBBLEGUM_CLOUD_ANDROID_ACTIVITY": os.getenv("BUBBLEGUM_CLOUD_ANDROID_ACTIVITY", "").strip(),
        "BUBBLEGUM_CLOUD_IOS_BUNDLE_ID": os.getenv("BUBBLEGUM_CLOUD_IOS_BUNDLE_ID", "").strip(),
    }

    missing: list[str] = []
    if not values["BUBBLEGUM_CLOUD_USERNAME"]:
        missing.append("BUBBLEGUM_CLOUD_USERNAME")
    if not values["BUBBLEGUM_CLOUD_ACCESS_KEY"]:
        missing.append("BUBBLEGUM_CLOUD_ACCESS_KEY")
    if values["BUBBLEGUM_CLOUD_PLATFORM"] not in {"android", "ios"}:
        missing.append("BUBBLEGUM_CLOUD_PLATFORM (android or ios)")
    if not values["BUBBLEGUM_CLOUD_DEVICE_NAME"]:
        missing.append("BUBBLEGUM_CLOUD_DEVICE_NAME")

    has_cloud_app = bool(values["BUBBLEGUM_CLOUD_APP"])
    has_cloud_app_id = bool(values["BUBBLEGUM_CLOUD_APP_ID"])
    has_android_pkg_activity = bool(
        values["BUBBLEGUM_CLOUD_ANDROID_PACKAGE"] and values["BUBBLEGUM_CLOUD_ANDROID_ACTIVITY"]
    )
    has_ios_bundle_id = bool(values["BUBBLEGUM_CLOUD_IOS_BUNDLE_ID"])

    if not (has_cloud_app or has_cloud_app_id or has_android_pkg_activity or has_ios_bundle_id):
        missing.append(
            "one of BUBBLEGUM_CLOUD_APP, BUBBLEGUM_CLOUD_APP_ID, "
            "(BUBBLEGUM_CLOUD_ANDROID_PACKAGE + BUBBLEGUM_CLOUD_ANDROID_ACTIVITY), "
            "BUBBLEGUM_CLOUD_IOS_BUNDLE_ID"
        )

    if missing:
        pytest.skip("Cloud device smoke requires: " + ", ".join(missing))

    cfg = build_cloud_harness_config()
    return (
        cfg.provider,
        cfg.appium_server_url,
        values,
        has_cloud_app,
        has_cloud_app_id,
        has_android_pkg_activity,
    )


def _assert_no_forbidden_keys(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in forbidden
            _assert_no_forbidden_keys(nested, forbidden)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_keys(nested, forbidden)


def test_cloud_device_smoke_collect_context_mvp() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")

    provider, appium_url, values, has_cloud_app, has_cloud_app_id, has_android_pkg_activity = _required_cloud_env()

    platform = values["BUBBLEGUM_CLOUD_PLATFORM"]
    if platform == "android":
        options_module = pytest.importorskip("appium.options.android")
        options = options_module.UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
    else:
        options_module = pytest.importorskip("appium.options.ios")
        options = options_module.XCUITestOptions()
        options.platform_name = "iOS"
        options.automation_name = "XCUITest"

    options.device_name = values["BUBBLEGUM_CLOUD_DEVICE_NAME"]

    if has_cloud_app:
        options.app = values["BUBBLEGUM_CLOUD_APP"]
    elif has_cloud_app_id:
        options.app = values["BUBBLEGUM_CLOUD_APP_ID"]
    elif platform == "android" and has_android_pkg_activity:
        options.app_package = values["BUBBLEGUM_CLOUD_ANDROID_PACKAGE"]
        options.app_activity = values["BUBBLEGUM_CLOUD_ANDROID_ACTIVITY"]
    elif platform == "ios":
        options.bundle_id = values["BUBBLEGUM_CLOUD_IOS_BUNDLE_ID"]

    options.set_capability("cloud:provider", provider)

    try:
        driver = appium_webdriver.Remote(appium_url, options=options)
    except Exception as exc:  # pragma: no cover - runtime-dependent skip path
        pytest.skip(f"Unable to start cloud device smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(
            adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
        )

        assert ui_context.channel == "mobile"
        detected_platform = adapter.platform
        if detected_platform not in {"android", "ios"}:
            cap_platform = str(getattr(driver, "capabilities", {}).get("platformName", "")).strip().lower()
            detected_platform = cap_platform
        assert detected_platform in {"android", "ios"}

        app_state = ui_context.app_state
        safe_blocks = (
            "context_inventory",
            "framework_detection",
            "webview_switch_diagnostics",
            "webview_switch_guardrails",
            "system_dialog_detection",
            "system_dialog_guardrails",
            "scroll_discovery",
        )
        for key in safe_blocks:
            assert key in app_state
            assert isinstance(app_state[key], dict)

        forbidden_keys = {
            "raw_xml",
            "hierarchy_xml",
            "raw_dom",
            "screenshot",
            "screenshot_bytes",
            "page_source",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
            "raw_capabilities",
            "username",
            "access_key",
            "credentials",
            "secrets",
            "full hierarchy payload",
        }
        _assert_no_forbidden_keys(app_state, forbidden_keys)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
