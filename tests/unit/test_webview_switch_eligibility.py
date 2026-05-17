from __future__ import annotations

import asyncio

from bubblegum.core.mobile.webview_switch_eligibility import evaluate_webview_switch_eligibility
from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ContextRequest


class _Driver:
    capabilities = {"platformName": "Android"}
    current_activity = ".MainActivity"
    page_source = "<hierarchy/>"
    contexts = ["NATIVE_APP"]
    current_context = "NATIVE_APP"

    def get_screenshot_as_png(self):
        return b""


def _base_kwargs():
    return {
        "context_inventory": {"has_webview_context": True, "webview_context_count": 1},
        "framework_detection": {"surface_type": "webview"},
        "webview_switch_diagnostics": {"status": "webview_candidate"},
        "webview_switch_guardrails": {"decision": "allowed"},
        "system_dialog_detection": {"dialog_detected": False, "owner": "app"},
    }


def test_opt_in_missing_blocks():
    out = evaluate_webview_switch_eligibility(**_base_kwargs(), explicit_opt_in=False)
    assert out["decision"] == "blocked"
    assert out["reason"] == "opt_in_missing"


def test_native_surface_blocks():
    k = _base_kwargs()
    k["framework_detection"] = {"surface_type": "android_native"}
    out = evaluate_webview_switch_eligibility(**k, explicit_opt_in=True)
    assert out["decision"] == "blocked"


def test_system_dialog_blocks():
    k = _base_kwargs()
    k["system_dialog_detection"] = {"dialog_detected": True, "owner": "system"}
    out = evaluate_webview_switch_eligibility(**k, explicit_opt_in=True)
    assert out["decision"] == "blocked"
    assert out["reason"] == "system_dialog_blocking"


def test_webview_candidate_allowed():
    out = evaluate_webview_switch_eligibility(**_base_kwargs(), explicit_opt_in=True, instruction="fill input field in webview")
    assert out["decision"] == "allowed"


def test_hybrid_candidate_allowed():
    k = _base_kwargs()
    k["framework_detection"] = {"surface_type": "hybrid"}
    k["webview_switch_diagnostics"] = {"status": "hybrid_candidate"}
    out = evaluate_webview_switch_eligibility(**k, explicit_opt_in=True, instruction="open link in webview")
    assert out["decision"] == "allowed"


def test_missing_webview_context_blocks():
    k = _base_kwargs()
    k["context_inventory"] = {"has_webview_context": False, "webview_context_count": 0}
    out = evaluate_webview_switch_eligibility(**k, explicit_opt_in=True, instruction="tap link")
    assert out["decision"] == "blocked"


def test_multiple_webviews_deferred():
    k = _base_kwargs()
    k["context_inventory"] = {"has_webview_context": True, "webview_context_count": 2}
    out = evaluate_webview_switch_eligibility(**k, explicit_opt_in=True, instruction="tap link")
    assert out["decision"] == "deferred"


def test_weak_instruction_hint_deferred():
    out = evaluate_webview_switch_eligibility(**_base_kwargs(), explicit_opt_in=True, instruction="tap continue")
    assert out["decision"] == "deferred"


def test_insufficient_metadata_unknown():
    out = evaluate_webview_switch_eligibility()
    assert out["decision"] == "unknown"


def test_switch_attempted_always_false_and_safe_evidence():
    out = evaluate_webview_switch_eligibility(**_base_kwargs(), explicit_opt_in=True, instruction="tap link")
    assert out["switch_attempted"] is False
    assert all("WEBVIEW_" not in token for token in out["evidence"])


def test_collect_context_attaches_webview_switch_eligibility():
    ctx = asyncio.run(AppiumAdapter(_Driver()).collect_context(ContextRequest(include_screenshot=False)))
    assert "webview_switch_eligibility" in ctx.app_state
    assert ctx.app_state["webview_switch_eligibility"]["switch_attempted"] is False
