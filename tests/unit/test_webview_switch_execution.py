from __future__ import annotations

from bubblegum.core.mobile.webview_switch_execution import (
    build_webview_switch_execution_plan,
    execute_webview_switch_guarded,
)


def _elig(decision: str = "allowed") -> dict:
    return {"decision": decision}


def _sel(decision: str = "selected", selected_context_type: str = "webview") -> dict:
    return {"decision": decision, "selected_context_type": selected_context_type, "reason": "unit_test"}


def test_opt_in_false_blocks_and_does_not_call_switch():
    called = {"switch": 0}

    def _switch(_selected):
        called["switch"] += 1

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(),
        webview_context_selection=_sel(),
        explicit_opt_in=False,
        switch_context=_switch,
    )
    assert out["switch_status"] == "blocked"
    assert out["reason"] == "opt_in_required"
    assert out["switch_attempted"] is False
    assert called["switch"] == 0


def test_eligibility_blocked_does_not_call_switch():
    called = {"switch": 0}

    def _switch(_selected):
        called["switch"] += 1

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig("blocked"), webview_context_selection=_sel(), explicit_opt_in=True, switch_context=_switch
    )
    assert out["switch_status"] == "blocked"
    assert out["switch_attempted"] is False
    assert called["switch"] == 0


def test_selection_deferred_does_not_call_switch():
    called = {"switch": 0}

    def _switch(_selected):
        called["switch"] += 1

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(), webview_context_selection=_sel(decision="deferred"), explicit_opt_in=True, switch_context=_switch
    )
    assert out["switch_status"] == "deferred"
    assert out["switch_attempted"] is False
    assert called["switch"] == 0


def test_selected_webview_with_opt_in_switches_then_restores():
    calls: list[tuple[str, object]] = []

    def _get_current():
        calls.append(("get", None))
        return "NATIVE_APP"

    def _switch(selected):
        calls.append(("switch", selected.get("decision")))

    def _restore(original):
        calls.append(("restore", original))

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(),
        webview_context_selection=_sel(),
        explicit_opt_in=True,
        get_current_context=_get_current,
        switch_context=_switch,
        restore_context=_restore,
    )
    assert out["switch_status"] == "switched"
    assert out["restore_status"] == "restored"
    assert out["restore_attempted"] is True
    assert calls == [("get", None), ("switch", "selected"), ("restore", "NATIVE_APP")]


def test_switch_failure_marks_failed_and_no_restore_attempted():
    called = {"restore": 0}

    def _switch(_selected):
        raise RuntimeError("WEBVIEW_secret exploded")

    def _restore(_original):
        called["restore"] += 1

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(),
        webview_context_selection=_sel(),
        explicit_opt_in=True,
        switch_context=_switch,
        restore_context=_restore,
    )
    assert out["switch_attempted"] is True
    assert out["switch_status"] == "failed"
    assert out["restore_attempted"] is False
    assert out["restore_status"] == "not_needed"
    assert called["restore"] == 0


def test_restore_failure_is_safe_and_sanitized():
    def _switch(_selected):
        return None

    def _restore(_original):
        raise RuntimeError("NATIVE_APP restore failed")

    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(),
        webview_context_selection=_sel(),
        explicit_opt_in=True,
        switch_context=_switch,
        restore_context=_restore,
    )
    assert out["switch_status"] == "switched"
    assert out["restore_attempted"] is True
    assert out["restore_status"] == "failed"


def test_exception_messages_and_raw_context_names_not_leaked():
    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(),
        webview_context_selection=_sel(),
        explicit_opt_in=True,
        switch_context=lambda _selected: (_ for _ in ()).throw(RuntimeError("WEBVIEW_com.secret leaked")),
    )
    rendered = str(out)
    assert "WEBVIEW_com.secret" not in rendered
    assert out["reason"] == "execution_error"


def test_switch_and_restore_attempted_flags_only_when_needed():
    out = execute_webview_switch_guarded(
        webview_switch_eligibility=_elig(), webview_context_selection=_sel(), explicit_opt_in=True, switch_context=lambda _selected: None
    )
    assert out["switch_attempted"] is True
    assert out["restore_attempted"] is False
    assert out["restore_status"] == "unknown"


def test_selected_metadata_insufficient_blocks():
    out = build_webview_switch_execution_plan(
        webview_switch_eligibility=_elig(), webview_context_selection=_sel(selected_context_type="unknown"), explicit_opt_in=True
    )
    assert out["switch_status"] == "blocked"
    assert out["reason"] == "selected_context_metadata_insufficient"
