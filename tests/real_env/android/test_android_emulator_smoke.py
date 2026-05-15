from __future__ import annotations

import asyncio
import json
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
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


def test_android_emulator_smoke_reporting_artifacts_are_safe(tmp_path) -> None:
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

        app_state = ui_context.app_state
        safe_keys = (
            "context_inventory",
            "framework_detection",
            "webview_switch_diagnostics",
            "webview_switch_guardrails",
        )
        for key in safe_keys:
            assert key in app_state

        metadata = {k: app_state[k] for k in safe_keys}
        metadata.update({
            "hierarchy_xml": "<hierarchy leaked>",
            "screenshot_bytes": "base64-leak",
            "provider_payload": {"token": "secret"},
            "raw_context_name": "WEBVIEW_com.example.app",
            "package_name": "com.example.app",
            "process_name": "com.example.app:renderer",
        })

        target_text = os.getenv("BUBBLEGUM_ANDROID_SMOKE_TARGET_TEXT", "").strip()
        action = "Android emulator context collection smoke"

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
            action = f"Android emulator target click smoke ({target_text})"

        step = StepResult(
            status="passed",
            action=action,
            confidence=1.0,
            target=ResolvedTarget(
                ref="android-smoke://context-collection",
                confidence=1.0,
                resolver_name="android_emulator_smoke",
                metadata=metadata,
            ),
        )

        json_path = tmp_path / "android_smoke_report.json"
        html_path = tmp_path / "android_smoke_report.html"
        write_json_report([step], path=json_path, title="Android Emulator Smoke Report")
        write_html_report([step], path=html_path, title="Android Emulator Smoke Report")

        assert json_path.exists()
        assert html_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["title"] == "Android Emulator Smoke Report"
        target_md = payload["results"][0]["target"]["metadata"]
        for key in safe_keys:
            assert key in target_md

        for forbidden in (
            "hierarchy_xml",
            "screenshot",
            "screenshot_bytes",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
        ):
            assert forbidden not in target_md

        html_text = html_path.read_text(encoding="utf-8")
        assert "Android Emulator Smoke Report" in html_text
        assert "WebView Dry-Run Diagnostics" in html_text
        for forbidden_text in (
            "WEBVIEW_com.example.app",
            "com.example.app",
            "base64-leak",
            "provider_payload",
            "<hierarchy leaked>",
        ):
            assert forbidden_text not in html_text
    finally:
        try:
            driver.quit()
        except Exception:
            pass
