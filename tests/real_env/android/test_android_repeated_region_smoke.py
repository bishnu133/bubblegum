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
        pytest.skip("Android repeated-region smoke requires: " + ", ".join(missing))

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


def _required_repeated_region_opt_in() -> tuple[str, str, str, str | None, str | None, bool]:
    enabled = os.getenv("BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE", "").strip() == "1"
    if not enabled:
        pytest.skip(
            "Android repeated-region smoke is opt-in; set BUBBLEGUM_ANDROID_REPEATED_REGION_SMOKE=1 to run it."
        )

    target_text = os.getenv("BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT", "").strip()
    anchor_text = os.getenv("BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT", "").strip()
    action_hint = os.getenv("BUBBLEGUM_ANDROID_REPEATED_ACTION_HINT", "").strip() or "tap"
    expect_status = os.getenv("BUBBLEGUM_ANDROID_REPEATED_EXPECT_STATUS", "").strip() or None
    require_resolved = os.getenv("BUBBLEGUM_ANDROID_REPEATED_REQUIRE_RESOLVED", "").strip() == "1"

    missing: list[str] = []
    if not target_text:
        missing.append("BUBBLEGUM_ANDROID_REPEATED_TARGET_TEXT")
    if not anchor_text:
        missing.append("BUBBLEGUM_ANDROID_REPEATED_ANCHOR_TEXT")

    if missing:
        pytest.skip("Android repeated-region smoke requires opt-in vars: " + ", ".join(missing))

    return target_text, anchor_text, action_hint, expect_status, require_resolved, enabled


def test_android_emulator_repeated_region_diagnostics_smoke(tmp_path) -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()
    target_text, anchor_text, action_hint, expect_status, require_resolved, _ = _required_repeated_region_opt_in()

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
        pytest.skip(f"Unable to start Android repeated-region smoke Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))

        instruction = f"{action_hint} {target_text} for {anchor_text}".strip()
        resolver = AppiumHierarchyResolver()
        candidates = resolver.resolve(
            StepIntent(
                instruction=instruction,
                channel="mobile",
                platform="android",
                action_type=action_hint if action_hint in {"tap", "click", "type", "select", "scroll", "swipe", "verify", "extract"} else "tap",
                context={"hierarchy_xml": ui_context.hierarchy_xml or "", "app_state": ui_context.app_state},
            )
        )

        assert candidates, "Expected at least one candidate from AppiumHierarchyResolver for repeated-region smoke input."

        with_diag = [c for c in candidates if isinstance(c.metadata.get("repeated_region_diagnostics"), dict)]
        assert with_diag, "Expected at least one candidate with repeated_region_diagnostics metadata."

        safe_diag = with_diag[0].metadata["repeated_region_diagnostics"]
        for required_key in (
            "status",
            "region_type",
            "matched_region_count",
            "candidate_count",
            "anchor_hint_type",
            "target_action_hint",
            "reason",
            "evidence",
            "warnings",
            "safe_metadata_only",
        ):
            assert required_key in safe_diag

        forbidden_keys = {
            "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
            "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace",
            "raw_instruction", "raw_anchor_text", "raw_candidate_text", "credentials", "secrets",
            "raw_capabilities", "full_hierarchy_payload",
        }
        assert forbidden_keys.isdisjoint(set(safe_diag.keys()))
        assert safe_diag.get("safe_metadata_only") is True

        allowed_statuses = {"resolved", "ambiguous", "no_anchor", "no_repeated_region", "unknown"}
        status = str(safe_diag.get("status", "unknown"))
        assert status in allowed_statuses

        if expect_status:
            assert status == expect_status
        if require_resolved:
            assert status == "resolved"

        step = StepResult(
            status="passed",
            action="Android repeated-region diagnostics smoke",
            confidence=1.0,
            target=ResolvedTarget(
                ref="android-repeated-region://diagnostics",
                confidence=1.0,
                resolver_name="android_repeated_region_smoke",
                metadata={
                    "repeated_region_diagnostics": {
                        **safe_diag,
                        "raw_xml": "<leak/>",
                        "page_source": "<source/>",
                        "provider_payload": {"token": "secret"},
                    }
                },
            ),
        )

        json_path = tmp_path / "android_repeated_region_smoke.json"
        html_path = tmp_path / "android_repeated_region_smoke.html"
        write_json_report([step], path=json_path, title="Android Repeated Region Smoke")
        write_html_report([step], path=html_path, title="Android Repeated Region Smoke")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert "repeated_region_summary" in payload.get("analytics", {})
        md = payload["results"][0]["target"]["metadata"]["repeated_region_diagnostics"]
        assert forbidden_keys.isdisjoint(set(md.keys()))

        html_text = html_path.read_text(encoding="utf-8")
        assert "Repeated Region Diagnostics" in html_text
        for forbidden_text in ("<leak/>", "provider_payload", "secret", "page_source"):
            assert forbidden_text not in html_text
    finally:
        try:
            driver.quit()
        except Exception:
            pass



def test_android_emulator_repeated_region_reporting_artifacts_are_safe(tmp_path) -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.android")

    appium_url, values, has_app = _required_android_env()
    target_text, anchor_text, action_hint, _expect_status, _require_resolved, _ = _required_repeated_region_opt_in()

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
        pytest.skip(f"Unable to start Android repeated-region reporting Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        ui_context = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))

        instruction = f"{action_hint} {target_text} for {anchor_text}".strip()
        resolver = AppiumHierarchyResolver()
        candidates = resolver.resolve(
            StepIntent(
                instruction=instruction,
                channel="mobile",
                platform="android",
                action_type=action_hint if action_hint in {"tap", "click", "type", "select", "scroll", "swipe", "verify", "extract"} else "tap",
                context={"hierarchy_xml": ui_context.hierarchy_xml or "", "app_state": ui_context.app_state},
            )
        )

        assert candidates, "Expected at least one candidate for repeated-region artifact validation."

        with_diag = [c for c in candidates if isinstance(c.metadata.get("repeated_region_diagnostics"), dict)]
        assert with_diag, "Expected repeated_region_diagnostics metadata in resolved candidates."

        step = StepResult(
            status="passed",
            action="Android repeated-region reporting artifact validation",
            confidence=1.0,
            target=ResolvedTarget(
                ref="android-repeated-region://reporting",
                confidence=1.0,
                resolver_name="android_repeated_region_reporting",
                metadata={"repeated_region_diagnostics": with_diag[0].metadata["repeated_region_diagnostics"]},
            ),
        )

        json_path = tmp_path / "android_repeated_region_reporting.json"
        html_path = tmp_path / "android_repeated_region_reporting.html"
        write_json_report([step], path=json_path, title="Android Repeated Region Reporting")
        write_html_report([step], path=html_path, title="Android Repeated Region Reporting")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert "repeated_region_summary" in payload.get("analytics", {})

        md = payload.get("results", [{}])[0].get("target", {}).get("metadata", {}).get("repeated_region_diagnostics", {})
        if md:
            assert isinstance(md, dict)

        html_text = html_path.read_text(encoding="utf-8")
        assert html_path.exists()
        assert "Repeated Region Diagnostics" in html_text

        forbidden_tokens = {
            "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
            "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace",
            "raw_instruction", "raw_anchor_text", "raw_candidate_text", "selected_candidate_ref",
            "credentials", "secrets", "raw_capabilities", "appium:options", "capabilities",
            "full_hierarchy_payload",
        }

        json_text = json_path.read_text(encoding="utf-8").lower()
        html_text_lower = html_text.lower()
        for token in forbidden_tokens:
            assert token not in json_text
            assert token not in html_text_lower
    finally:
        try:
            driver.quit()
        except Exception:
            pass
