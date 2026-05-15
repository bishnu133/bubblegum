from __future__ import annotations

from bubblegum.core.mobile.webview_guardrails import evaluate_webview_switch_guardrails


def _inv(has_webview=True, count=1):
    return {
        "has_webview_context": has_webview,
        "webview_context_count": count,
        "has_native_context": True,
    }


def _fd(surface):
    return {"surface_type": surface}


def _diag(status):
    return {"status": status}


def test_opt_in_missing_blocks_even_when_candidate():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(), framework_detection=_fd("webview"), webview_switch_diagnostics=_diag("webview_candidate")
    )
    assert out["decision"] == "blocked"
    assert out["reason"] == "opt_in_missing"


def test_webview_opt_in_with_context_allows():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(),
        framework_detection=_fd("webview"),
        webview_switch_diagnostics=_diag("webview_candidate"),
        explicit_opt_in=True,
        target_hint="web login link",
    )
    assert out["decision"] == "allowed"
    assert out["reason"] == "eligible_webview"


def test_hybrid_opt_in_with_context_allows():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(),
        framework_detection=_fd("hybrid"),
        webview_switch_diagnostics=_diag("hybrid_candidate"),
        explicit_opt_in=True,
        action_type="click",
        target_hint="open browser link",
    )
    assert out["decision"] == "allowed"
    assert out["reason"] == "eligible_hybrid"


def test_native_surface_blocks():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(), framework_detection=_fd("android_native"), webview_switch_diagnostics=_diag("native_only"), explicit_opt_in=True
    )
    assert out["decision"] == "blocked"


def test_system_dialog_unsupported():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(), framework_detection=_fd("system_dialog"), webview_switch_diagnostics=_diag("not_applicable"), explicit_opt_in=True
    )
    assert out["decision"] == "unsupported"


def test_unknown_surface_safe_block_or_unsupported():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(has_webview=False), framework_detection=_fd("unknown"), webview_switch_diagnostics=_diag("unknown"), explicit_opt_in=True
    )
    assert out["decision"] in {"blocked", "unsupported"}
    assert out["reason"] == "unknown_surface"


def test_missing_webview_context_unsupported():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(has_webview=False),
        framework_detection=_fd("webview"),
        webview_switch_diagnostics=_diag("webview_candidate"),
        explicit_opt_in=True,
        target_hint="open web url",
    )
    assert out["decision"] == "unsupported"
    assert out["reason"] == "webview_context_missing"


def test_multiple_webviews_deferred_without_selection_policy():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(has_webview=True, count=2),
        framework_detection=_fd("hybrid"),
        webview_switch_diagnostics=_diag("hybrid_candidate"),
        explicit_opt_in=True,
        target_hint="web checkout link",
    )
    assert out["decision"] == "deferred"


def test_weak_hint_deferred_when_hint_provided():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(),
        framework_detection=_fd("webview"),
        webview_switch_diagnostics=_diag("webview_candidate"),
        explicit_opt_in=True,
        target_hint="continue",
    )
    assert out["decision"] == "deferred"
    assert out["reason"] == "web_like_hint_missing"


def test_switch_attempted_always_false_and_evidence_safe():
    out = evaluate_webview_switch_guardrails(
        context_inventory=_inv(), framework_detection=_fd("hybrid"), webview_switch_diagnostics=_diag("hybrid_candidate")
    )
    assert out["switch_attempted"] is False
    for token in out["evidence"]:
        assert isinstance(token, str)
        assert "WEBVIEW_" not in token
        assert "<" not in token
