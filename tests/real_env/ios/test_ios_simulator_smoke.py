from __future__ import annotations

import asyncio
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest
from tests.real_env.conftest import require_real_env_enabled


pytestmark = [
    pytest.mark.real_env,
    pytest.mark.ios_simulator,
    pytest.mark.ios_device,
    pytest.mark.hybrid_webview,
    pytest.mark.system_dialog,
    pytest.mark.slow,
]


def _required_ios_env() -> tuple[str, dict[str, str], bool]:
    require_real_env_enabled()

    values = {
        "BUBBLEGUM_APPIUM_SERVER_URL": os.getenv("BUBBLEGUM_APPIUM_SERVER_URL", "").strip(),
        "BUBBLEGUM_IOS_DEVICE_NAME": os.getenv("BUBBLEGUM_IOS_DEVICE_NAME", "").strip(),
        "BUBBLEGUM_IOS_APP": os.getenv("BUBBLEGUM_IOS_APP", "").strip(),
        "BUBBLEGUM_IOS_BUNDLE_ID": os.getenv("BUBBLEGUM_IOS_BUNDLE_ID", "").strip(),
        "BUBBLEGUM_IOS_PLATFORM_VERSION": os.getenv("BUBBLEGUM_IOS_PLATFORM_VERSION", "").strip(),
        "BUBBLEGUM_IOS_AUTOMATION_NAME": os.getenv("BUBBLEGUM_IOS_AUTOMATION_NAME", "").strip(),
    }

    missing: list[str] = []
    if not values["BUBBLEGUM_APPIUM_SERVER_URL"]:
        missing.append("BUBBLEGUM_APPIUM_SERVER_URL")
    if not values["BUBBLEGUM_IOS_DEVICE_NAME"]:
        missing.append("BUBBLEGUM_IOS_DEVICE_NAME")

    has_app = bool(values["BUBBLEGUM_IOS_APP"])
    has_bundle_id = bool(values["BUBBLEGUM_IOS_BUNDLE_ID"])
    if not has_app and not has_bundle_id:
        missing.append("BUBBLEGUM_IOS_APP (or BUBBLEGUM_IOS_BUNDLE_ID)")

    if missing:
        pytest.skip("iOS simulator smoke requires: " + ", ".join(missing))

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


def _assert_no_forbidden_keys(value: object, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in forbidden
            _assert_no_forbidden_keys(nested, forbidden)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_forbidden_keys(nested, forbidden)


def test_ios_simulator_smoke_collect_context_mvp() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.ios")

    appium_url, values, has_app = _required_ios_env()

    options = options_module.XCUITestOptions()
    options.platform_name = "iOS"
    options.device_name = values["BUBBLEGUM_IOS_DEVICE_NAME"]
    options.automation_name = values["BUBBLEGUM_IOS_AUTOMATION_NAME"] or "XCUITest"

    if values["BUBBLEGUM_IOS_PLATFORM_VERSION"]:
        options.platform_version = values["BUBBLEGUM_IOS_PLATFORM_VERSION"]

    if has_app:
        options.app = values["BUBBLEGUM_IOS_APP"]
    else:
        options.bundle_id = values["BUBBLEGUM_IOS_BUNDLE_ID"]

    try:
        driver = appium_webdriver.Remote(appium_url, options=options)
    except Exception as exc:  # pragma: no cover - runtime-dependent skip path
        pytest.skip(f"Unable to start iOS simulator smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(
            adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
        )

        assert adapter.channel == "mobile"
        assert adapter.platform == "ios" or str(getattr(driver, "capabilities", {}).get("platformName", "")).lower() == "ios"

        assert ui_context.screenshot is None
        assert ui_context.hierarchy_xml is None or isinstance(ui_context.hierarchy_xml, str)

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
            "raw_dom",
            "screenshot_bytes",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
            "raw_capabilities",
            "credentials",
            "secrets",
            "hierarchy_xml",
            "page_source",
        }
        _assert_no_forbidden_keys(app_state, forbidden_keys)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
