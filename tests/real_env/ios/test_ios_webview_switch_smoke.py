from __future__ import annotations

import asyncio
import os

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ContextRequest, ValidationPlan
from tests.real_env.conftest import require_real_env_enabled

pytestmark = [
    pytest.mark.real_env,
    pytest.mark.ios_simulator,
    pytest.mark.ios_device,
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


def _required_ios_webview_env() -> tuple[str, dict[str, str], bool]:
    require_real_env_enabled()
    if os.getenv("BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE", "").strip() != "1":
        pytest.skip(
            "iOS WebView switch smoke is opt-in; set "
            "BUBBLEGUM_IOS_WEBVIEW_SWITCH_SMOKE=1 to run it."
        )

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
        pytest.skip("iOS WebView switch smoke requires: " + ", ".join(missing))

    return values["BUBBLEGUM_APPIUM_SERVER_URL"], values, has_app


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


def _build_ref(ref_text: str) -> dict[str, object]:
    return {"by": "xpath", "value": ref_text, "metadata": {}}


def test_ios_webview_switch_smoke_validate_extract_real_env() -> None:
    appium_webdriver = pytest.importorskip("appium.webdriver")
    options_module = pytest.importorskip("appium.options.ios")

    appium_url, values, has_app = _required_ios_webview_env()

    validate_text = os.getenv("BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT", "").strip()
    extract_ref = os.getenv("BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF", "").strip()
    require_switch = os.getenv("BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH", "").strip() == "1"
    expect_status = os.getenv("BUBBLEGUM_IOS_WEBVIEW_EXPECT_STATUS", "").strip() or None
    allowed_op = os.getenv("BUBBLEGUM_IOS_WEBVIEW_ALLOWED_OPERATION", "").strip().lower()

    allowed_ops = ["verify", "extract"]
    if allowed_op in {"validate", "extract"}:
        allowed_ops = ["verify"] if allowed_op == "validate" else ["extract"]

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
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Unable to start iOS WebView switch Appium session: {exc}")

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
        inventory = app_state.get("context_inventory") if isinstance(app_state.get("context_inventory"), dict) else {}
        diagnostics = app_state.get("webview_switch_diagnostics") if isinstance(app_state.get("webview_switch_diagnostics"), dict) else {}

        assert inventory, "Expected context_inventory metadata from real-env Appium context collection."
        assert diagnostics, "Expected webview_switch_diagnostics metadata for WebView candidate analysis."
        _assert_metadata_safe(app_state)

        run_validate = bool(validate_text) and "verify" in allowed_ops
        run_extract = bool(extract_ref) and "extract" in allowed_ops
        if not run_validate and not run_extract:
            pytest.skip(
                "No WebView operation inputs provided. Set BUBBLEGUM_IOS_WEBVIEW_VALIDATE_TEXT and/or "
                "BUBBLEGUM_IOS_WEBVIEW_EXTRACT_REF for operation-path smoke."
            )

        switch_attempted = False
        switched = False

        if run_validate:
            md = dict(app_state)
            adapter._webview_validate_metadata = {
                "webview_context_selection": md.get("webview_context_selection"),
                "webview_switch_eligibility": md.get("webview_switch_eligibility"),
            }
            out = asyncio.run(
                adapter.validate(ValidationPlan(assertion_type="text_visible", expected_value=validate_text, timeout_ms=3000))
            )
            assert isinstance(out.passed, bool)
            execution = adapter._last_webview_switch_execution or {}
            wiring = adapter._prepare_webview_switch_metadata_for_operation(
                operation_type="validate",
                instruction=validate_text,
                target_metadata=adapter._webview_validate_metadata,
                config=adapter._config,
            )
            assert "webview_switch_wiring_plan" in wiring
            _assert_metadata_safe(wiring)
            if wiring["webview_switch_wiring_plan"].get("switch_ready"):
                switch_attempted = True
                assert "webview_switch_execution" in execution
                switch_exec = execution.get("webview_switch_execution") if isinstance(execution, dict) else {}
                assert isinstance(switch_exec, dict)
                switched = bool(switch_exec.get("switch_attempted"))
                assert "restore_status" in switch_exec
                _assert_metadata_safe(switch_exec)
                if expect_status:
                    assert str(switch_exec.get("switch_status")) == expect_status

        if run_extract:
            ref = _build_ref(extract_ref)
            ref["metadata"] = {
                "webview_context_selection": app_state.get("webview_context_selection"),
                "webview_switch_eligibility": app_state.get("webview_switch_eligibility"),
            }
            _ = asyncio.run(adapter.extract_text(ref))
            wiring = adapter._prepare_webview_switch_metadata_for_operation(
                operation_type="extract",
                instruction=None,
                target_metadata=ref["metadata"],
                config=adapter._config,
            )
            assert "webview_switch_wiring_plan" in wiring
            _assert_metadata_safe(wiring)
            execution = ref["metadata"].get("webview_switch_execution")
            if wiring["webview_switch_wiring_plan"].get("switch_ready"):
                switch_attempted = True
                assert isinstance(execution, dict), "Expected webview_switch_execution metadata when switch path is ready."
                switched = switched or bool(execution.get("switch_attempted"))
                assert "restore_status" in execution
                _assert_metadata_safe(execution)
                if expect_status:
                    assert str(execution.get("switch_status")) == expect_status
            _assert_metadata_safe(ref["metadata"])

        assert not hasattr(adapter, "_last_execute_webview_switch_execution")
        if require_switch and switch_attempted and not switched:
            pytest.fail(
                "BUBBLEGUM_IOS_WEBVIEW_REQUIRE_SWITCH=1 but no WebView switch occurred. "
                "Ensure app exposes stable WebView context and matching target input."
            )
    finally:
        try:
            driver.quit()
        except Exception:
            pass
