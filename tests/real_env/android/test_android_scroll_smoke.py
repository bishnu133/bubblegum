from __future__ import annotations

import asyncio
import json
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.mobile.scroll_discovery import build_mobile_scroll_discovery_plan
from bubblegum.core.mobile.scroll_discovery import execute_bounded_mobile_scroll_search
from bubblegum.core.mobile.scroll_resolution import resolve_with_bounded_scroll
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepResult
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


def test_android_emulator_scroll_resolution_reporting_artifacts_are_safe(tmp_path) -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()

    if os.getenv("BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION", "").strip() != "1":
        pytest.skip(
            "Android scroll resolution reporting validation is opt-in; set "
            "BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1 to run bounded scroll resolution reporting checks."
        )

    target_text = os.getenv("BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT", "").strip()
    if not target_text:
        pytest.skip(
            "Android scroll resolution reporting validation requires "
            "BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT when opt-in is enabled."
        )

    max_scrolls = int(os.getenv("BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS", "3"))

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
        pytest.skip(f"Unable to start Android scroll resolution reporting Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)

        def _collect_state() -> dict:
            ui_context = asyncio.run(
                adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
            )
            app_state = dict(ui_context.app_state)
            app_state.setdefault("channel", "mobile")
            return app_state

        initial_state = _collect_state()
        hierarchy_xml = str(initial_state.get("hierarchy_xml") or "")
        scroll_plan = build_mobile_scroll_discovery_plan(
            instruction=f"find {target_text}",
            target_hint=target_text,
            hierarchy_xml=hierarchy_xml,
            platform="android",
            app_state=initial_state,
            max_scrolls=max_scrolls,
        )

        resolve_state = {"found": bool(target_text and target_text.lower() in hierarchy_xml.lower())}

        def _resolve_once() -> dict[str, bool]:
            return {"found": bool(resolve_state.get("found"))}

        def _collect_context_for_resolver() -> dict:
            app_state = _collect_state()
            live_xml = str(app_state.get("hierarchy_xml") or "")
            resolve_state["found"] = bool(target_text.lower() in live_xml.lower())
            return app_state

        resolution = resolve_with_bounded_scroll(
            driver=driver,
            instruction=f"find {target_text}",
            target_hint=target_text,
            resolve_once=_resolve_once,
            collect_context=_collect_context_for_resolver,
            scroll_plan=scroll_plan,
            explicit_opt_in=True,
            max_scrolls=max_scrolls,
        )

        step = StepResult(
            status="passed",
            action=f"Android scroll resolution reporting smoke ({target_text})",
            confidence=1.0,
            target=ResolvedTarget(
                ref="android-scroll-resolution://reporting",
                confidence=1.0,
                resolver_name="android_scroll_resolution_smoke",
                metadata={
                    "scroll_discovery": initial_state.get("scroll_discovery", {}),
                    "scroll_resolution": {
                        **resolution,
                        "hierarchy_xml": "<raw hierarchy leak>",
                        "page_source": "<raw source leak>",
                        "provider_payload": {"secret": "token"},
                        "raw_context_name": "WEBVIEW_com.example.app",
                        "package_name": "com.example.app",
                        "process_name": "com.example.app:renderer",
                        "exception_trace": "traceback...",
                        "raw_instruction": "click secret button",
                        "credentials": "username:password",
                        "raw_capabilities": {"appium:udid": "emulator-5554"},
                        "full_hierarchy_payload": {"xml": "<hierarchy />"},
                    },
                },
            ),
        )

        json_path = tmp_path / "android_scroll_resolution_report.json"
        html_path = tmp_path / "android_scroll_resolution_report.html"
        write_json_report([step], path=json_path, title="Android Scroll Resolution Reporting Smoke")
        write_html_report([step], path=html_path, title="Android Scroll Resolution Reporting Smoke")

        assert json_path.exists()
        assert html_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["title"] == "Android Scroll Resolution Reporting Smoke"
        assert "scroll_resolution_summary" in payload["analytics"]

        target_md = payload["results"][0]["target"]["metadata"]
        assert "scroll_resolution" in target_md
        assert "scroll_discovery" in target_md

        for forbidden in (
            "raw_xml",
            "hierarchy_xml",
            "raw_dom",
            "screenshot_bytes",
            "page_source",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
            "exception_trace",
            "raw_instruction",
            "credentials",
            "secrets",
            "raw_capabilities",
            "full_hierarchy_payload",
        ):
            assert forbidden not in target_md["scroll_resolution"]

        html_text = html_path.read_text(encoding="utf-8")
        assert "Android Scroll Resolution Reporting Smoke" in html_text
        assert "Scroll Resolution Summary" in html_text

        for forbidden_text in (
            "<raw hierarchy leak>",
            "<raw source leak>",
            "WEBVIEW_com.example.app",
            "com.example.app",
            "username:password",
            "appium:udid",
            "traceback...",
        ):
            assert forbidden_text not in html_text
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def test_android_emulator_scroll_resolution_opt_in_smoke() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()

    if os.getenv("BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION", "").strip() != "1":
        pytest.skip(
            "Android scroll resolution smoke is metadata-only by default; set "
            "BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1 for explicit bounded scroll opt-in."
        )

    target_text = os.getenv("BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT", "").strip()
    if not target_text:
        pytest.skip(
            "Android scroll resolution smoke requires BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT "
            "when scroll resolution opt-in is enabled."
        )

    max_scrolls = int(os.getenv("BUBBLEGUM_ANDROID_SCROLL_MAX_SCROLLS", "3"))

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
        pytest.skip(f"Unable to start Android scroll resolution Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)

        def _collect_state() -> dict:
            ui_context = asyncio.run(
                adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True))
            )
            app_state = dict(ui_context.app_state)
            app_state.setdefault("channel", "mobile")
            return app_state

        initial_state = _collect_state()
        hierarchy_xml = str(initial_state.get("hierarchy_xml") or "")
        scroll_plan = build_mobile_scroll_discovery_plan(
            instruction=f"find {target_text}",
            target_hint=target_text,
            hierarchy_xml=hierarchy_xml,
            platform="android",
            app_state=initial_state,
            max_scrolls=max_scrolls,
        )

        resolve_state = {"found": bool(target_text and target_text.lower() in hierarchy_xml.lower())}

        def _resolve_once() -> dict[str, bool]:
            return {"found": bool(resolve_state.get("found"))}

        def _collect_context_for_resolver() -> dict:
            app_state = _collect_state()
            live_xml = str(app_state.get("hierarchy_xml") or "")
            resolve_state["found"] = bool(target_text.lower() in live_xml.lower())
            return app_state

        result = resolve_with_bounded_scroll(
            driver=driver,
            instruction=f"find {target_text}",
            target_hint=target_text,
            resolve_once=_resolve_once,
            collect_context=_collect_context_for_resolver,
            scroll_plan=scroll_plan,
            explicit_opt_in=True,
            max_scrolls=max_scrolls,
        )

        assert result["enabled"] is True
        assert result["attempted"] is True
        assert result["max_scrolls"] <= 10
        assert result["attempt_count"] <= result["max_scrolls"]

        for forbidden in (
            "hierarchy_xml",
            "screenshot",
            "screenshot_bytes",
            "provider_payload",
            "raw_context_name",
            "package_name",
            "process_name",
            "context_names",
        ):
            assert forbidden not in result

        if result["final_status"] != "found":
            pytest.fail(
                "BUBBLEGUM_ANDROID_ENABLE_SCROLL_RESOLUTION=1 with "
                "BUBBLEGUM_ANDROID_SCROLL_TARGET_TEXT explicitly requested bounded scroll resolution, "
                "but the target was not found within bounded attempts."
            )
    finally:
        try:
            driver.quit()
        except Exception:
            pass
