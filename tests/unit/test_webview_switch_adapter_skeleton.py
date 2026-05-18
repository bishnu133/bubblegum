from __future__ import annotations

import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ValidationPlan


class _Element:
    text = "Login"

    def get_attribute(self, _attr: str):
        return None


class _SwitchTo:
    def context(self, _value):
        raise AssertionError("driver.switch_to.context must not be called in phase 20P")


class _Driver:
    capabilities = {"platformName": "Android"}
    page_source = "Login"
    current_activity = ".MainActivity"
    switch_to = _SwitchTo()

    def find_element(self, *_args, **_kwargs):
        return _Element()



def _cfg_enabled_for(ops: list[str]) -> BubblegumConfig:
    return BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=True,
            webview_switching_mode="opt_in",
            webview_switch_allowed_operations=ops,
        )
    )


def test_validate_default_behavior_unchanged_and_no_switch_attempt(monkeypatch):
    adapter = AppiumAdapter(_Driver())
    seen = {}

    def _fake_prepare(**kwargs):
        seen.update(kwargs)
        return {"webview_switch_wiring_plan": {"switch_ready": False, "safe_metadata_only": True}}

    monkeypatch.setattr(adapter, "_prepare_webview_switch_metadata_for_operation", _fake_prepare)

    plan = ValidationPlan(assertion_type="text_visible", expected_value="Login")
    result = asyncio.run(adapter.validate(plan))

    assert result.passed is True
    assert result.actual_value == "Login"
    assert seen["operation_type"] == "validate"


def test_extract_default_behavior_unchanged_and_no_switch_attempt(monkeypatch):
    adapter = AppiumAdapter(_Driver())
    seen = {}

    def _fake_prepare(**kwargs):
        seen.update(kwargs)
        return {"webview_switch_wiring_plan": {"switch_ready": False, "safe_metadata_only": True}}

    monkeypatch.setattr(adapter, "_prepare_webview_switch_metadata_for_operation", _fake_prepare)

    result = asyncio.run(adapter.extract_text('{"by": "id", "value": "login"}'))

    assert result == "Login"
    assert seen["operation_type"] == "extract"


def test_config_enabled_validate_prepares_wiring_only_and_execute_not_wired(monkeypatch):
    adapter = AppiumAdapter(_Driver())
    adapter._config = _cfg_enabled_for(["verify", "extract"])

    called = {"guarded": False}

    def _fake_guarded(*_args, **_kwargs):
        called["guarded"] = True
        raise AssertionError("execute_webview_switch_guarded must not be called")

    monkeypatch.setattr("bubblegum.adapters.mobile.appium.adapter.execute_webview_switch_guarded", _fake_guarded, raising=False)

    out = adapter._prepare_webview_switch_metadata_for_operation(
        operation_type="validate",
        instruction="Login",
        target_metadata={
            "webview_switch_eligibility": {"decision": "allowed"},
            "webview_context_selection": {"decision": "selected", "selected_context_type": "webview", "selected_context": "WEBVIEW_raw"},
        },
        config=adapter._config,
    )["webview_switch_wiring_plan"]

    assert out["switch_ready"] is True
    assert "WEBVIEW_raw" not in str(out)
    assert called["guarded"] is False


def test_config_enabled_extract_prepares_wiring_only():
    adapter = AppiumAdapter(_Driver())
    adapter._config = _cfg_enabled_for(["verify", "extract"])

    out = adapter._prepare_webview_switch_metadata_for_operation(
        operation_type="extract",
        instruction=None,
        target_metadata={
            "webview_switch_eligibility": {"decision": "allowed"},
            "webview_context_selection": {"decision": "selected", "selected_context_type": "WEBVIEW_something"},
        },
        config=adapter._config,
    )["webview_switch_wiring_plan"]

    assert out["switch_ready"] is True
    assert out["context_selection_decision"] == "selected"
