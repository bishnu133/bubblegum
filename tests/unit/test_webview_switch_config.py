from __future__ import annotations

import pytest
from pydantic import ValidationError

from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.mobile.webview_switch_config import is_webview_switching_enabled_for_operation


def test_default_webview_switching_config_is_safe_and_off():
    cfg = BubblegumConfig()
    wv = cfg.webview_switching
    assert wv.enable_webview_switching is False
    assert wv.webview_switching_mode == "off"
    assert wv.webview_switch_allowed_operations == []
    assert wv.require_restore_context is True
    assert wv.fail_closed_on_restore_failure is True
    assert wv.webview_context_selection_policy == "single_webview_only"
    assert wv.max_webview_switch_attempts == 1


def test_invalid_mode_rejected():
    with pytest.raises(ValidationError):
        WebviewSwitchingConfig(webview_switching_mode="sometimes")


def test_invalid_selection_policy_rejected():
    with pytest.raises(ValidationError):
        WebviewSwitchingConfig(webview_context_selection_policy="round_robin")


def test_invalid_max_attempts_rejected():
    with pytest.raises(ValidationError):
        WebviewSwitchingConfig(max_webview_switch_attempts=0)


def test_helper_operation_not_allowed_blocks():
    cfg = BubblegumConfig(webview_switching=WebviewSwitchingConfig(enable_webview_switching=True, webview_switching_mode="opt_in"))
    out = is_webview_switching_enabled_for_operation(config=cfg, operation_type="verify")
    assert out["enabled"] is False
    assert out["reason"] == "operation_not_allowed"


def test_helper_opt_in_and_operation_allowed_enables_metadata_only():
    cfg = BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=True,
            webview_switching_mode="opt_in",
            webview_switch_allowed_operations=["verify", "extract"],
        )
    )
    out = is_webview_switching_enabled_for_operation(config=cfg, operation_type="verify")
    assert out == {
        "enabled": True,
        "reason": "enabled",
        "operation_type": "verify",
        "mode": "opt_in",
        "safe_metadata_only": True,
    }


def test_helper_default_config_disabled_by_config():
    out = is_webview_switching_enabled_for_operation(config=BubblegumConfig(), operation_type="extract")
    assert out["enabled"] is False
    assert out["reason"] == "disabled_by_config"
