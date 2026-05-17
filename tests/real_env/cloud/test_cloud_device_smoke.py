from __future__ import annotations

import asyncio
import json
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
from tests.real_env.cloud.harness import build_cloud_harness_config, cloud_config_safe_summary
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


def test_cloud_device_reporting_artifacts_are_safe(tmp_path) -> None:
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
        pytest.skip(f"Unable to start cloud device reporting Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(
            adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
        )

        app_state = ui_context.app_state
        safe_keys = (
            "framework_detection",
            "webview_switch_diagnostics",
            "webview_switch_guardrails",
            "system_dialog_detection",
            "system_dialog_guardrails",
            "scroll_discovery",
        )
        for key in safe_keys:
            assert key in app_state

        metadata = {k: app_state[k] for k in safe_keys}
        metadata["cloud_provider_summary"] = cloud_config_safe_summary()
        if "mobile_memory_signature" in app_state:
            metadata["mobile_memory_signature"] = app_state["mobile_memory_signature"]

        metadata.update({
            "raw_xml": "<xml leaked>",
            "hierarchy_xml": "<hierarchy leaked>",
            "raw_dom": "<dom leaked>",
            "screenshot": "base64-image",
            "screenshot_bytes": "base64-bytes",
            "page_source": "<page source>",
            "provider_payload": {"token": "secret"},
            "raw_context_name": "WEBVIEW_com.example.cloud",
            "package_name": "com.example.cloud",
            "process_name": "WebContent",
            "raw_capabilities": {"udid": "device-udid"},
            "credentials": {"username": values["BUBBLEGUM_CLOUD_USERNAME"]},
            "username": values["BUBBLEGUM_CLOUD_USERNAME"],
            "access_key": values["BUBBLEGUM_CLOUD_ACCESS_KEY"],
            "secrets": [values["BUBBLEGUM_CLOUD_ACCESS_KEY"]],
            "full hierarchy payload": "leaked-full-hierarchy",
            "Appium raw capabilities": "do-not-include",
            "provider-specific secret tokens": "do-not-include",
        })

        step = StepResult(
            status="passed",
            action="cloud device context collection reporting smoke",
            confidence=1.0,
            target=ResolvedTarget(
                ref="cloud-smoke://context-collection",
                confidence=1.0,
                resolver_name="cloud_device_smoke",
                metadata=metadata,
            ),
        )

        json_path = tmp_path / "cloud_smoke_report.json"
        html_path = tmp_path / "cloud_smoke_report.html"
        write_json_report([step], path=json_path, title="Cloud Device Smoke Report")
        write_html_report([step], path=html_path, title="Cloud Device Smoke Report")

        assert json_path.exists()
        assert html_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["title"] == "Cloud Device Smoke Report"
        assert isinstance(payload.get("analytics"), dict)

        analytics = payload["analytics"]
        for key in (
            "webview_diagnostics_summary",
            "system_dialog_summary",
            "system_dialog_guardrails_summary",
            "scroll_discovery_summary",
            "mobile_memory_signature_summary",
        ):
            assert key in analytics

        target_md = payload["results"][0]["target"]["metadata"]
        for key in safe_keys:
            assert key in target_md
        if "mobile_memory_signature" in metadata:
            assert "mobile_memory_signature" in target_md

        for forbidden in (
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
            "Appium raw capabilities",
            "provider-specific secret tokens",
        ):
            assert forbidden not in target_md

        serialized = json.dumps(payload)
        html_text = html_path.read_text(encoding="utf-8")
        for forbidden_text in (
            "<xml leaked>",
            "<hierarchy leaked>",
            "<dom leaked>",
            "base64-image",
            "base64-bytes",
            "WEBVIEW_com.example.cloud",
            "com.example.cloud",
            "provider_payload",
            "device-udid",
            "leaked-full-hierarchy",
            "do-not-include",
            values["BUBBLEGUM_CLOUD_USERNAME"],
            values["BUBBLEGUM_CLOUD_ACCESS_KEY"],
        ):
            assert forbidden_text not in serialized
            assert forbidden_text not in html_text

        assert "Cloud Device Smoke Report" in html_text
        assert "WebView Dry-Run Diagnostics" in html_text
        assert "System Dialog Detection" in html_text
        assert "Scroll Discovery" in html_text
        if "mobile_memory_signature" in metadata:
            assert "Mobile Memory Signature" in html_text
    finally:
        try:
            driver.quit()
        except Exception:
            pass
