from __future__ import annotations

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.mobile.webview_switch_execution import execute_webview_switch_guarded


class _Driver:
    capabilities = {"platformName": "Android"}


def _adapter() -> AppiumAdapter:
    return AppiumAdapter(_Driver())


def _cfg(*, enabled: bool, mode: str, ops: list[str]) -> BubblegumConfig:
    return BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=enabled,
            webview_switching_mode=mode,
            webview_switch_allowed_operations=ops,
        )
    )


def _eligible() -> dict:
    return {"decision": "allowed", "safe_metadata_only": True}


def _selected() -> dict:
    return {
        "decision": "selected",
        "selected_context_type": "webview",
        "selected_context_index": 0,  # should never leak
        "safe_metadata_only": True,
    }


def test_wiring_plan_default_config_no_switch():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="execute", instruction=None, target_metadata={}, config=BubblegumConfig()
    )["webview_switch_wiring_plan"]
    assert out["enabled"] is False
    assert out["reason"] in {"disabled_by_config", "mode_off", "operation_not_allowed"}
    assert out["switch_ready"] is False


def test_wiring_plan_mode_off_no_switch():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="execute", instruction=None, target_metadata={}, config=_cfg(enabled=True, mode="off", ops=["execute"])
    )["webview_switch_wiring_plan"]
    assert out["enabled"] is False
    assert out["reason"] == "mode_off"


def test_wiring_plan_operation_not_allowed_no_switch():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="validate", instruction=None, target_metadata={}, config=_cfg(enabled=True, mode="opt_in", ops=["extract"])
    )["webview_switch_wiring_plan"]
    assert out["enabled"] is False
    assert out["reason"] == "operation_not_allowed"


def test_wiring_plan_missing_eligibility_no_switch():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="execute", instruction=None, target_metadata={}, config=_cfg(enabled=True, mode="opt_in", ops=["execute"])
    )["webview_switch_wiring_plan"]
    assert out["enabled"] is True
    assert out["switch_ready"] is False
    assert out["reason"] == "missing_eligibility"


def test_wiring_plan_missing_context_selection_no_switch():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="execute",
        instruction=None,
        target_metadata={"webview_switch_eligibility": _eligible()},
        config=_cfg(enabled=True, mode="opt_in", ops=["execute"]),
    )["webview_switch_wiring_plan"]
    assert out["enabled"] is True
    assert out["switch_ready"] is False
    assert out["reason"] == "missing_context_selection"


def test_opt_in_fake_switch_success_and_restore():
    calls: list[tuple[str, object]] = []

    def _get() -> str:
        calls.append(("get", None))
        return "NATIVE_APP"

    def _switch(selection: dict) -> None:
        calls.append(("switch", selection.get("selected_context_type")))

    def _restore(original: str | None) -> None:
        calls.append(("restore", original))

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_eligible(),
        webview_context_selection=_selected(),
        explicit_opt_in=True,
        get_current_context=_get,
        switch_context=_switch,
        restore_context=_restore,
    )
    assert out["switch_status"] == "switched"
    assert out["restore_status"] == "restored"
    assert calls == [("get", None), ("switch", "webview"), ("restore", "NATIVE_APP")]


def test_opt_in_fake_switch_failure_safe_metadata():
    def _switch(_selection: dict) -> None:
        raise RuntimeError("WEBVIEW_com.example boom")

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_eligible(),
        webview_context_selection=_selected(),
        explicit_opt_in=True,
        get_current_context=lambda: "NATIVE_APP",
        switch_context=_switch,
        restore_context=lambda _orig: None,
    )
    assert out["switch_status"] == "failed"
    assert "switch_failed" in out["warnings"]
    assert "WEBVIEW" not in str(out)


def test_opt_in_fake_restore_failure_safe_metadata():
    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_eligible(),
        webview_context_selection=_selected(),
        explicit_opt_in=True,
        get_current_context=lambda: "NATIVE_APP",
        switch_context=lambda _selection: None,
        restore_context=lambda _orig: (_ for _ in ()).throw(RuntimeError("restore WEBVIEW_com.example failed")),
    )
    assert out["switch_status"] == "switched"
    assert out["restore_status"] == "failed"
    assert "restore_failed" in out["warnings"]
    assert "WEBVIEW_com.example" not in str(out)


def test_wiring_plan_raw_context_name_not_leaked():
    out = _adapter()._prepare_webview_switch_metadata_for_operation(
        operation_type="execute",
        instruction="fill form",
        target_metadata={
            "webview_switch_eligibility": _eligible(),
            "webview_context_selection": _selected(),
        },
        config=_cfg(enabled=True, mode="opt_in", ops=["execute"]),
    )["webview_switch_wiring_plan"]
    assert out["switch_ready"] is True
    assert out["context_selection_decision"] == "selected"
    assert "selected_context" not in out
    assert "WEBVIEW_com.example" not in str(out)
