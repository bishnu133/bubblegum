from __future__ import annotations

import asyncio
import json
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepIntent, StepResult
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
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
        pytest.skip("Android icon smoke requires: " + ", ".join(missing))

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


def _required_icon_opt_in() -> tuple[str, str | None, bool]:
    enabled = os.getenv("BUBBLEGUM_ANDROID_ICON_SMOKE", "").strip() == "1"
    if not enabled:
        pytest.skip("Android icon smoke is opt-in; set BUBBLEGUM_ANDROID_ICON_SMOKE=1 to run it.")

    target = os.getenv("BUBBLEGUM_ANDROID_ICON_TARGET", "").strip()
    if not target:
        pytest.skip("Android icon smoke requires BUBBLEGUM_ANDROID_ICON_TARGET when opt-in is enabled.")

    expect_status = os.getenv("BUBBLEGUM_ANDROID_ICON_EXPECT_STATUS", "").strip() or None
    require_resolved = os.getenv("BUBBLEGUM_ANDROID_ICON_REQUIRE_RESOLVED", "").strip() == "1"
    return target, expect_status, require_resolved


def test_android_emulator_icon_detection_smoke() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()
    icon_target, expect_status, require_resolved = _required_icon_opt_in()

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
        pytest.skip(f"Unable to start Android icon smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))

        resolver = AppiumHierarchyResolver()
        candidates = resolver.resolve(
            StepIntent(
                instruction=f"tap {icon_target} icon",
                channel="mobile",
                platform="android",
                action_type="tap",
                context={"hierarchy_xml": ui_context.hierarchy_xml or "", "app_state": ui_context.app_state},
            )
        )

        with_icon = [c for c in candidates if isinstance(c.metadata.get("icon_detection"), dict)]
        assert with_icon, "Expected at least one candidate with icon_detection metadata for icon smoke input."

        diag = with_icon[0].metadata["icon_detection"]
        for required_key in (
            "status",
            "icon_hint_type",
            "target_icon",
            "candidate_count",
            "matched_candidate_count",
            "reason",
            "evidence",
            "warnings",
            "safe_metadata_only",
        ):
            assert required_key in diag

        forbidden_keys = {
            "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
            "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace",
            "raw_instruction", "raw_candidate_text", "raw_content_desc", "raw_resource_id", "credentials",
            "secrets", "raw_capabilities", "full_hierarchy_payload",
        }
        assert forbidden_keys.isdisjoint(set(diag.keys()))
        assert diag.get("safe_metadata_only") is True

        allowed_statuses = {"resolved", "ambiguous", "no_icon_candidate", "unsupported", "unknown"}
        status = str(diag.get("status", "unknown"))
        assert status in allowed_statuses

        if expect_status:
            assert status == expect_status
        if require_resolved:
            assert status == "resolved"

        if candidates:
            assert any(isinstance(c.metadata.get("icon_detection"), dict) for c in candidates)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def test_android_emulator_icon_detection_reporting_artifacts_are_safe(tmp_path) -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()
    icon_target, _, _ = _required_icon_opt_in()

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
        pytest.skip(f"Unable to start Android icon reporting Appium session: {exc}")

    forbidden_keys = {
        "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
        "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace",
        "raw_instruction", "raw_candidate_text", "raw_content_desc", "raw_resource_id", "credentials",
        "secrets", "raw_capabilities", "appium_raw_capabilities", "full_hierarchy_payload",
    }

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))

        resolver = AppiumHierarchyResolver()
        candidates = resolver.resolve(
            StepIntent(
                instruction=f"tap {icon_target} icon",
                channel="mobile",
                platform="android",
                action_type="tap",
                context={"hierarchy_xml": ui_context.hierarchy_xml or "", "app_state": ui_context.app_state},
            )
        )

        with_icon = [c for c in candidates if isinstance(c.metadata.get("icon_detection"), dict)]
        assert with_icon, "Expected at least one candidate with icon_detection metadata for icon smoke input."

        icon_md = dict(with_icon[0].metadata["icon_detection"])
        icon_md.update({
            "hierarchy_xml": "<hierarchy leaked>",
            "screenshot_bytes": "base64-leak",
            "provider_payload": {"token": "secret"},
            "raw_context_name": "WEBVIEW_com.example.app",
            "package_name": "com.example.app",
            "process_name": "com.example.app:renderer",
            "raw_capabilities": {"platformName": "Android"},
            "appium_raw_capabilities": {"deviceName": "emulator-5554"},
            "full_hierarchy_payload": {"xml": "<hierarchy/>"},
            "credentials": "username:password",
            "secrets": "token",
        })

        step = StepResult(
            status="passed",
            action=f"Android icon detection reporting smoke ({icon_target})",
            confidence=1.0,
            target=ResolvedTarget(
                ref="android-icon-smoke://reporting",
                confidence=1.0,
                resolver_name="appium_hierarchy",
                metadata={"icon_detection": icon_md},
            ),
        )

        json_path = tmp_path / "android_icon_detection_report.json"
        html_path = tmp_path / "android_icon_detection_report.html"
        write_json_report([step], path=json_path, title="Android Icon Detection Reporting Smoke")
        write_html_report([step], path=html_path, title="Android Icon Detection Reporting Smoke")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["title"] == "Android Icon Detection Reporting Smoke"
        analytics = payload.get("analytics", {})
        assert "icon_detection_summary" in analytics

        target_md = payload["results"][0]["target"]["metadata"]
        assert "icon_detection" in target_md
        icon_out = target_md["icon_detection"]
        assert icon_out.get("safe_metadata_only") is True
        assert forbidden_keys.isdisjoint(set(icon_out.keys()))

        json_text = json_path.read_text(encoding="utf-8")
        html_text = html_path.read_text(encoding="utf-8")
        assert "Icon Detection" in html_text

        for forbidden in forbidden_keys:
            assert forbidden not in json_text
            assert forbidden not in html_text

        for forbidden_text in (
            "<hierarchy leaked>",
            "base64-leak",
            "WEBVIEW_com.example.app",
            "com.example.app",
            "username:password",
        ):
            assert forbidden_text not in json_text
            assert forbidden_text not in html_text
    finally:
        try:
            driver.quit()
        except Exception:
            pass
