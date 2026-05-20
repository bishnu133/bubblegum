from __future__ import annotations

import json
import pathlib

from bubblegum.core.mobile.webview_readiness import build_webview_readiness_plan


def test_disabled_plan():
    out = build_webview_readiness_plan(enabled=False)
    assert out["status"] == "not_checked"
    assert out["reason"] == "disabled"
    assert out["safe_metadata_only"] is True


def test_missing_context_inventory_waiting():
    out = build_webview_readiness_plan(enabled=True, context_inventory=None)
    assert out["status"] == "waiting_for_webview_context"
    assert out["reason"] == "missing_context_inventory"


def test_no_webview_context_waiting():
    out = build_webview_readiness_plan(enabled=True, context_inventory={"webview_context_count": 0})
    assert out["status"] == "waiting_for_webview_context"
    assert out["reason"] == "no_webview_context"


def test_selected_context_available():
    out = build_webview_readiness_plan(
        enabled=True,
        context_inventory={"webview_context_count": 2},
        webview_context_selection={"decision": "selected", "selected_context_index": 1},
    )
    assert out["status"] == "context_available"
    assert out["reason"] == "selected_context_available"


def test_switch_ready_waiting_for_target_plan():
    out = build_webview_readiness_plan(
        enabled=True,
        context_inventory={"webview_context_count": 1},
        webview_context_selection={"decision": "selected", "selected_context_index": 0},
        webview_switch_wiring_plan={"switch_ready": True},
    )
    assert out["status"] == "waiting_for_target"
    assert out["reason"] == "switch_ready_target_pending"
    assert out["target_wait_attempted"] is False


def test_invalid_timeout_and_poll_values_safely_handled():
    out = build_webview_readiness_plan(enabled=True, timeout_ms=0, poll_interval_ms=10)
    assert out["status"] == "failed_closed"
    assert out["reason"] == "invalid_timeout"
    assert out["timeout_ms"] > 0
    assert out["poll_interval_ms"] >= 100


def test_max_refresh_attempts_clamped():
    out = build_webview_readiness_plan(enabled=True, max_context_refresh_attempts=999)
    assert out["max_context_refresh_attempts"] == 3


def test_raw_context_names_not_leaked():
    out = build_webview_readiness_plan(
        enabled=True,
        context_inventory={"webview_context_count": 1, "raw_context_names": ["WEBVIEW_SECRET"]},
        webview_context_selection={"decision": "selected", "selected_context_index": 0, "selected_context": "WEBVIEW_SECRET"},
    )
    rendered = str(out)
    assert "WEBVIEW_SECRET" not in rendered
    assert "raw_context_names" not in rendered


def test_output_is_json_safe():
    out = build_webview_readiness_plan(enabled=True, context_inventory={"webview_context_count": 1})
    json.dumps(out)


def test_helper_is_wired_into_appium_adapter_for_validate_extract():
    adapter_text = (pathlib.Path(__file__).resolve().parents[2] / "bubblegum/adapters/mobile/appium/adapter.py").read_text(
        encoding="utf-8"
    )
    assert "build_webview_readiness_plan" in adapter_text
