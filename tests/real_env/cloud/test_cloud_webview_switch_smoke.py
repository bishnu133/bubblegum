from __future__ import annotations

import asyncio
import json
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ContextRequest, ResolvedTarget, StepResult, ValidationPlan
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report
from tests.real_env.cloud.harness import (
    build_cloud_capabilities,
    build_cloud_harness_config,
    cloud_config_safe_summary,
)
from tests.real_env.conftest import require_real_env_enabled

pytestmark = [
    pytest.mark.real_env,
    pytest.mark.cloud_device,
    pytest.mark.hybrid_webview,
    pytest.mark.slow,
]

FORBIDDEN_METADATA_KEYS = {
    "raw_context_name",
    "raw_context_names",
    "context_name",
    "context_names",
    "selected_context_name",
    "original_context_name",
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "page_source",
    "screenshot",
    "screenshot_bytes",
    "provider_payload",
    "raw_capabilities",
    "credentials",
    "secrets",
    "exception_trace",
    "exception_message",
}


def _required_cloud_webview_env() -> tuple[str, str, str, str, str, str, str | None]:
    require_real_env_enabled()
    if os.getenv("BUBBLEGUM_CLOUD_DEVICE", "").strip() != "1":
        pytest.skip("Cloud device smoke harness is disabled. Set BUBBLEGUM_CLOUD_DEVICE=1 to opt in.")
    if os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE", "").strip() != "1":
        pytest.skip("Cloud WebView switch smoke is disabled. Set BUBBLEGUM_CLOUD_WEBVIEW_SWITCH_SMOKE=1 to opt in.")

    cfg = build_cloud_harness_config()
    caps = build_cloud_capabilities()

    platform = os.getenv("BUBBLEGUM_CLOUD_PLATFORM", "").strip().lower()
    username = os.getenv("BUBBLEGUM_CLOUD_USERNAME", "").strip()
    access_key = os.getenv("BUBBLEGUM_CLOUD_ACCESS_KEY", "").strip()
    device_name = os.getenv("BUBBLEGUM_CLOUD_DEVICE_NAME", "").strip()
    app = os.getenv("BUBBLEGUM_CLOUD_APP", "").strip()
    app_id = os.getenv("BUBBLEGUM_CLOUD_APP_ID", "").strip()

    missing: list[str] = []
    if not username:
        missing.append("BUBBLEGUM_CLOUD_USERNAME")
    if not access_key:
        missing.append("BUBBLEGUM_CLOUD_ACCESS_KEY")
    if platform not in {"android", "ios"}:
        missing.append("BUBBLEGUM_CLOUD_PLATFORM (android or ios)")
    if not device_name:
        missing.append("BUBBLEGUM_CLOUD_DEVICE_NAME")
    if not (app or app_id):
        missing.append("BUBBLEGUM_CLOUD_APP or BUBBLEGUM_CLOUD_APP_ID")
    if missing:
        pytest.skip("Cloud WebView switch smoke requires: " + ", ".join(missing))

    return cfg.provider, cfg.appium_server_url, platform, username, access_key, device_name, json.dumps(caps)


def _iter_keys_recursive(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _iter_keys_recursive(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_keys_recursive(child)


def _assert_metadata_safe(value) -> None:
    leaked = FORBIDDEN_METADATA_KEYS.intersection(set(_iter_keys_recursive(value)))
    assert not leaked, f"Forbidden metadata keys found: {sorted(leaked)}"


def _assert_no_forbidden_tokens(value, username: str, access_key: str) -> None:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    for token in ("WEBVIEW_", "NATIVE_APP", "raw_context_name", "context_names", "provider_payload", "raw_capabilities", "secrets"):
        assert token not in text
    assert username not in text
    assert access_key not in text


def _build_ref(ref_text: str) -> dict[str, object]:
    return {"by": "xpath", "value": ref_text, "metadata": {}}


def test_cloud_webview_switch_smoke_validate_extract_real_env() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")

    _, appium_url, _, username, access_key, _, _ = _required_cloud_webview_env()

    validate_text = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT", "").strip()
    extract_ref = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF", "").strip()
    require_switch = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH", "").strip() == "1"
    expect_status = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_EXPECT_STATUS", "").strip() or None
    allowed_op = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_ALLOWED_OPERATION", "").strip().lower()

    allowed_ops = ["verify", "extract"]
    if allowed_op in {"validate", "extract"}:
        allowed_ops = ["verify"] if allowed_op == "validate" else ["extract"]

    capabilities = build_cloud_capabilities()

    try:
        driver = appium_webdriver.Remote(appium_url, desired_capabilities=capabilities)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Unable to start cloud WebView switch Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        adapter._config = BubblegumConfig(
            webview_switching=WebviewSwitchingConfig(
                enable_webview_switching=True,
                webview_switching_mode="opt_in",
                webview_switch_allowed_operations=allowed_ops,
                require_restore_context=True,
                fail_closed_on_restore_failure=True,
            )
        )

        ctx = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))
        app_state = ctx.app_state if isinstance(ctx.app_state, dict) else {}
        _assert_metadata_safe(app_state)

        run_validate = bool(validate_text) and "verify" in allowed_ops
        run_extract = bool(extract_ref) and "extract" in allowed_ops
        if not run_validate and not run_extract:
            pytest.skip("No cloud WebView operation inputs provided. Set BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT and/or BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF.")

        switch_ready = False
        switched = False

        if run_validate:
            adapter._webview_validate_metadata = {
                "webview_context_selection": app_state.get("webview_context_selection"),
                "webview_switch_eligibility": app_state.get("webview_switch_eligibility"),
            }
            out = asyncio.run(adapter.validate(ValidationPlan(assertion_type="text_visible", expected_value=validate_text, timeout_ms=3000)))
            assert isinstance(out.passed, bool)
            wiring = adapter._prepare_webview_switch_metadata_for_operation("validate", validate_text, adapter._webview_validate_metadata, adapter._config)
            assert "webview_switch_wiring_plan" in wiring
            _assert_metadata_safe(wiring)
            if wiring["webview_switch_wiring_plan"].get("switch_ready"):
                switch_ready = True
                execution = adapter._last_webview_switch_execution or {}
                assert "webview_switch_execution" in execution
                switch_exec = execution.get("webview_switch_execution")
                assert isinstance(switch_exec, dict)
                assert "restore_status" in switch_exec
                switched = bool(switch_exec.get("switch_attempted"))
                if expect_status:
                    assert str(switch_exec.get("switch_status")) == expect_status
                _assert_metadata_safe(switch_exec)

        if run_extract:
            ref = _build_ref(extract_ref)
            ref["metadata"] = {
                "webview_context_selection": app_state.get("webview_context_selection"),
                "webview_switch_eligibility": app_state.get("webview_switch_eligibility"),
            }
            _ = asyncio.run(adapter.extract_text(ref))
            wiring = adapter._prepare_webview_switch_metadata_for_operation("extract", None, ref["metadata"], adapter._config)
            assert "webview_switch_wiring_plan" in wiring
            _assert_metadata_safe(wiring)
            if wiring["webview_switch_wiring_plan"].get("switch_ready"):
                switch_ready = True
                execution = ref["metadata"].get("webview_switch_execution")
                assert isinstance(execution, dict)
                assert "restore_status" in execution
                switched = switched or bool(execution.get("switch_attempted"))
                if expect_status:
                    assert str(execution.get("switch_status")) == expect_status
                _assert_metadata_safe(execution)
            _assert_metadata_safe(ref["metadata"])

        assert not hasattr(adapter, "_last_execute_webview_switch_execution")
        if require_switch and switch_ready and not switched:
            pytest.fail("BUBBLEGUM_CLOUD_WEBVIEW_REQUIRE_SWITCH=1 but no WebView switch occurred.")

        _assert_no_forbidden_tokens(app_state, username, access_key)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def test_cloud_webview_switch_reporting_artifacts_are_safe(tmp_path) -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")

    _, appium_url, _, username, access_key, _, _ = _required_cloud_webview_env()
    validate_text = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT", "").strip()
    extract_ref = os.getenv("BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF", "").strip()
    if not validate_text and not extract_ref:
        pytest.skip("Artifact validation needs operation metadata; set BUBBLEGUM_CLOUD_WEBVIEW_VALIDATE_TEXT and/or BUBBLEGUM_CLOUD_WEBVIEW_EXTRACT_REF.")

    capabilities = build_cloud_capabilities()

    try:
        driver = appium_webdriver.Remote(appium_url, desired_capabilities=capabilities)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Unable to start cloud WebView reporting Appium session: {exc}")

    try:
        adapter = AppiumAdapter(driver)
        adapter._config = BubblegumConfig(webview_switching=WebviewSwitchingConfig(enable_webview_switching=True, webview_switching_mode="opt_in", webview_switch_allowed_operations=["verify", "extract"], require_restore_context=True, fail_closed_on_restore_failure=True))
        ctx = asyncio.run(adapter.collect_context(ContextRequest(include_screenshot=False, include_hierarchy=True)))
        app_state = ctx.app_state if isinstance(ctx.app_state, dict) else {}
        safe_md: dict[str, object] = {"cloud_provider_summary": cloud_config_safe_summary()}
        for key in ("context_inventory", "webview_switch_diagnostics", "webview_context_selection", "webview_switch_eligibility"):
            if key in app_state:
                safe_md[key] = app_state[key]
        if validate_text:
            adapter._webview_validate_metadata = {"webview_context_selection": app_state.get("webview_context_selection"), "webview_switch_eligibility": app_state.get("webview_switch_eligibility")}
            _ = asyncio.run(adapter.validate(ValidationPlan(assertion_type="text_visible", expected_value=validate_text, timeout_ms=3000)))
            safe_md.update(adapter._prepare_webview_switch_metadata_for_operation("validate", validate_text, adapter._webview_validate_metadata, adapter._config))
            if isinstance(adapter._last_webview_switch_execution, dict):
                safe_md.update(adapter._last_webview_switch_execution)
        if extract_ref:
            ref = _build_ref(extract_ref)
            ref["metadata"] = {"webview_context_selection": app_state.get("webview_context_selection"), "webview_switch_eligibility": app_state.get("webview_switch_eligibility")}
            _ = asyncio.run(adapter.extract_text(ref))
            safe_md.update(ref["metadata"])

        step = StepResult(status="passed", action="Cloud WebView artifact smoke", confidence=1.0, target=ResolvedTarget(ref="cloud-webview://switch", confidence=1.0, resolver_name="cloud_webview_smoke", metadata=safe_md))
        json_path = tmp_path / "cloud_webview_switch_report.json"
        html_path = tmp_path / "cloud_webview_switch_report.html"
        write_json_report([step], path=json_path, title="Cloud WebView Switch Smoke Report")
        write_html_report([step], path=html_path, title="Cloud WebView Switch Smoke Report")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert "cloud_provider_summary" in payload["analytics"]
        assert "webview_switch_wiring_plan_summary" in payload["analytics"]
        assert "webview_switch_execution_summary" in payload["analytics"]
        html_text = html_path.read_text(encoding="utf-8")
        assert "Cloud Provider Summary" in html_text
        assert "WebView Switch Wiring Plan" in html_text
        if "webview_switch_execution" in json.dumps(payload):
            assert "WebView Switch Execution" in html_text
        _assert_metadata_safe(payload)
        _assert_no_forbidden_tokens(payload, username, access_key)
        _assert_no_forbidden_tokens(html_text, username, access_key)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
