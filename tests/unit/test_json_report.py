from __future__ import annotations

import asyncio
import json

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.config import BubblegumConfig, WebviewSwitchingConfig
from bubblegum.core.schemas import ArtifactRef, ErrorInfo, ResolvedTarget, ResolverTrace, StepResult, ValidationPlan
from bubblegum.reporting.html_report import build_report_analytics
from bubblegum.reporting.json_report import write_json_report


class _WebviewFakeElement:
    def __init__(self, text: str = ""):
        self.text = text

    def get_attribute(self, name: str):
        return "attr-text" if name == "text" else ""


class _WebviewFakeDriver:
    capabilities = {"platformName": "Android"}
    page_source = "hello"
    contexts = ["NATIVE_APP", "WEBVIEW_test"]
    current_context = "NATIVE_APP"

    class _SwitchTo:
        def __init__(self, outer):
            self._outer = outer

        def context(self, name: str):
            self._outer.current_context = name

    def __init__(self):
        self.switch_to = self._SwitchTo(self)

    def find_element(self, *_args, **_kwargs):
        return _WebviewFakeElement("base-text")


def _webview_cfg(enabled=True, mode="opt_in", ops=None):
    return BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=enabled,
            webview_switching_mode=mode,
            webview_switch_allowed_operations=ops or ["verify", "extract"],
        )
    )


def _webview_metadata():
    return {
        "webview_switch_eligibility": {"decision": "allowed", "safe_metadata_only": True},
        "webview_context_selection": {
            "decision": "selected",
            "selected_context_type": "webview",
            "selected_context_index": 0,
            "safe_metadata_only": True,
        },
    }


def _build_fake_wiring_execution_metadata_for_extract():
    ad = AppiumAdapter(_WebviewFakeDriver())
    ad._config = _webview_cfg()
    ref = {"by": "id", "value": "a", "metadata": _webview_metadata()}
    ad._webview_switch_context = lambda _sel: None
    ad._webview_restore_context = lambda _orig: None
    out = asyncio.run(ad.extract_text(ref))
    assert out == "base-text"
    return ref["metadata"]


def _build_fake_wiring_execution_metadata_for_validate():
    ad = AppiumAdapter(_WebviewFakeDriver())
    ad._config = _webview_cfg()
    ad._webview_validate_metadata = _webview_metadata()
    ad._run_assertion = lambda _plan: (True, "ok")
    ad._webview_switch_context = lambda _sel: None
    ad._webview_restore_context = lambda _orig: None
    out = asyncio.run(ad.validate(ValidationPlan(assertion_type="text_visible", expected_value="x")))
    assert out.passed is True
    assert isinstance(ad._last_webview_switch_execution, dict)
    return dict(ad._last_webview_switch_execution)


class _Driver:
    capabilities = {"platformName": "Android"}


def _sample_result() -> StepResult:
    target = ResolvedTarget(ref='role=button[name="Login"]', confidence=0.91, resolver_name="exact_text")
    trace_target = ResolvedTarget(ref='role=button[name="Log In"]', confidence=0.74, resolver_name="fuzzy_text")
    artifact = ArtifactRef(type="screenshot", path="artifacts/step1.png", timestamp="2026-05-04T00:00:00+00:00")
    error = ErrorInfo(error_type="ResolverError", message="fallback used", resolver_name="fuzzy_text")
    trace = ResolverTrace(resolver_name="fuzzy_text", duration_ms=12, candidates=[trace_target], can_run=True)
    return StepResult(
        status="recovered",
        action="Click Login",
        target=target,
        confidence=0.91,
        artifacts=[artifact],
        duration_ms=55,
        error=error,
        traces=[trace],
    )


def test_write_json_report_creates_payload_and_file(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = _sample_result()

    out = write_json_report([result], path=report_path, title="My Report")

    assert out == report_path.resolve()
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["version"] == "1"
    assert isinstance(payload["generated_at"], str)
    assert payload["title"] == "My Report"
    assert isinstance(payload["analytics"], dict)
    assert isinstance(payload["results"], list)
    assert len(payload["results"]) == 1


def test_analytics_matches_build_report_analytics(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [_sample_result(), StepResult(status="failed", action="Submit", confidence=0.42)]

    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["analytics"] == build_report_analytics(results)


def test_nested_fields_serialize_as_dicts_and_lists(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    write_json_report([_sample_result()], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    step = payload["results"][0]
    assert isinstance(step["error"], dict)
    assert isinstance(step["traces"], list)
    assert isinstance(step["artifacts"], list)
    assert isinstance(step["target"], dict)


def test_empty_results_payload(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    write_json_report([], path=report_path)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["analytics"]["total"] == 0
    assert payload["results"] == []


def test_json_report_preserves_safe_hydration_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    target = ResolvedTarget(
        ref='text="Login"',
        confidence=0.9,
        resolver_name="ocr",
        metadata={
            "hydration_status": "hydrated",
            "hydration_reason": "hydrated_text_ref",
            "hydration_source": "ocr",
            "hydration_strategy": "text",
            "hydration_channel": "web",
            "hydration_original_ref": "ocr://block/0",
            "hydration_hydrated_ref": 'text="Login"',
        },
    )
    result = StepResult(status="passed", action="Click Login", target=target, confidence=0.9)
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["hydration_status"] == "hydrated"
    assert md["hydration_reason"] == "hydrated_text_ref"


def test_json_report_redacts_unsafe_hydration_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    target = ResolvedTarget(
        ref='text="Login"',
        confidence=0.9,
        resolver_name="ocr",
        metadata={
            "hydration_status": "not_hydrated",
            "match_count": 2,
            "hierarchy_xml": "<root/>",
            "screenshot_bytes": "abc",
            "base64": "zzz",
            "raw_payload": "secret",
            "provider_response": "body",
            "candidate_dump": ["x"],
        },
    )
    result = StepResult(status="failed", action="Click Login", target=target, confidence=0.9)
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["hydration_status"] == "not_hydrated"
    assert md["match_count"] == "2"
    assert "hierarchy_xml" not in md
    assert "screenshot_bytes" not in md
    assert "base64" not in md
    assert "raw_payload" not in md
    assert "provider_response" not in md
    assert "candidate_dump" not in md


def test_json_report_includes_hydration_analytics_summary(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="Click Login",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Login"',
                confidence=0.9,
                resolver_name="ocr",
                metadata={
                    "hydration_status": "hydrated",
                    "hydration_source": "ocr",
                    "hydration_strategy": "text",
                    "hydration_channel": "web",
                    "hydration_reason": "hydrated_text_ref",
                    "hydration_original_ref": "ocr://block/1",
                },
            ),
        ),
        StepResult(status="failed", action="Submit", confidence=0.4),
    ]

    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    hs = payload["analytics"]["hydration_summary"]
    assert hs["total_events"] == 1
    assert hs["status_counts"]["hydrated"] == 1
    assert hs["status_counts"]["not_hydrated"] == 0
    assert hs["status_counts"]["blocked"] == 0
    assert hs["by_source"] == {"ocr": 1}
    assert hs["by_strategy"] == {"text": 1}
    assert hs["by_channel"] == {"web": 1}
    assert hs["by_reason"] == {"hydrated_text_ref": 1}


def test_json_report_preserves_safe_retry_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=1.0,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=1.0,
            resolver_name="x",
            metadata={
                "retry_attempts": 1,
                "retry_transient": True,
                "retry_reason": "timeout",
                "retry_adapter": "playwright",
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["retry_attempts"] == 1
    assert md["retry_transient"] is True
    assert md["retry_reason"] == "timeout"
    assert md["retry_adapter"] == "playwright"


def test_json_report_redacts_unsafe_retry_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="failed",
        action="Click",
        confidence=0.2,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.2,
            resolver_name="x",
            metadata={
                "retry_attempts": 1,
                "retry_reason": "timeout",
                "retry_stack": "Traceback ...",
                "retry_payload": "secret",
                "retry_secrets": "token",
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["retry_attempts"] == 1
    assert md["retry_reason"] == "timeout"
    assert "retry_stack" not in md
    assert "retry_payload" not in md
    assert "retry_secrets" not in md


def test_json_report_preserves_safe_wait_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=1.0,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=1.0,
            resolver_name="x",
            metadata={
                "wait_used": True,
                "wait_mode": "visible",
                "wait_outcome": "success",
                "wait_adapter": "playwright",
                "wait_duration_ms": 10,
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["wait_used"] is True
    assert md["wait_mode"] == "visible"
    assert md["wait_outcome"] == "success"
    assert md["wait_adapter"] == "playwright"


def test_json_report_redacts_unsafe_wait_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="failed",
        action="Click",
        confidence=0.2,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.2,
            resolver_name="x",
            metadata={
                "wait_used": True,
                "wait_mode": "visible",
                "wait_outcome": "failed",
                "wait_adapter": "appium",
                "wait_stack": "Traceback ...",
                "wait_payload": "secret",
                "wait_secrets": "token",
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["wait_mode"] == "visible"
    assert "wait_stack" not in md
    assert "wait_payload" not in md
    assert "wait_secrets" not in md


def test_json_report_graph_signals_preserved_and_redacted(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "graph_signals": {
                    "label_for_match": True,
                    "same_row_match": False,
                    "score_hint": 0.286,
                    "reason": "ok",
                    "hierarchy_xml": "<xml/>",
                    "raw_payload": {"secret": "x"},
                    "full_graph": {"nodes": []},
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    gs = payload["results"][0]["target"]["metadata"]["graph_signals"]
    assert gs["label_for_match"] is True
    assert gs["same_row_match"] is False
    assert gs["score_hint"] == 0.286
    assert gs["reason"] == "ok"
    assert "hierarchy_xml" not in gs
    assert "raw_payload" not in gs
    assert "full_graph" not in gs


def test_json_report_graph_query_diagnostics_preserves_safe_fields(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "graph_query_diagnostics": {
                    "status": "applied",
                    "relation_type": "label_for",
                    "anchor_resolution": "resolved",
                    "scope_resolution": "none",
                    "matched_ids": ["a", "b"],
                    "excluded_ids": ["x"],
                    "ambiguity": False,
                    "reasons": ["ok"],
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    gq = payload["results"][0]["target"]["metadata"]["graph_query_diagnostics"]
    assert gq["status"] == "applied"
    assert gq["relation_type"] == "label_for"
    assert gq["matched_ids"] == ["a", "b"]
    assert gq["reasons"] == ["ok"]


def test_json_report_graph_query_diagnostics_redacts_unsafe_fields(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "graph_query_diagnostics": {
                    "status": "applied",
                    "relation_type": "label_for",
                    "raw_snapshot": "secret",
                    "snapshot": "secret",
                    "hierarchy_xml": "<xml/>",
                    "provider_payload": {"secret": "x"},
                    "nodes": [{"id": "n1"}],
                    "edges": [{"from": "n1", "to": "n2"}],
                    "raw_attributes": {"a": 1},
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    gq = payload["results"][0]["target"]["metadata"]["graph_query_diagnostics"]
    assert gq["status"] == "applied"
    for key in [
        "raw_snapshot",
        "snapshot",
        "hierarchy_xml",
        "provider_payload",
        "nodes",
        "edges",
        "raw_attributes",
    ]:
        assert key not in gq

def test_json_report_preserves_safe_webview_diagnostics_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Login",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "webview_switch_diagnostics": {
                    "status": "dry_run",
                    "recommended_context": "WEBVIEW_1",
                    "switch_required_future": True,
                    "switch_attempted": False,
                    "reason": "dom_detected",
                    "evidence": ["script tag"],
                    "warnings": ["deferred"],
                    "safe_metadata_only": True,
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["webview_switch_diagnostics"]
    assert md["status"] == "dry_run"
    assert md["recommended_context"] == "WEBVIEW_1"
    assert md["switch_required_future"] is True


def test_json_report_redacts_unsafe_webview_diagnostics_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Login",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "webview_switch_diagnostics": {
                    "status": "dry_run",
                    "raw_xml": "<xml/>",
                    "raw_dom": "<dom/>",
                    "screenshot_bytes": "abc",
                    "provider_payload": {"secret": "x"},
                    "package_name": "pkg",
                    "process_name": "proc",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    wd = payload["results"][0]["target"]["metadata"]["webview_switch_diagnostics"]
    assert wd["status"] == "dry_run"
    assert "raw_xml" not in wd
    assert "raw_dom" not in wd
    assert "screenshot_bytes" not in wd
    assert "provider_payload" not in wd
    assert "package_name" not in wd
    assert "process_name" not in wd


def test_json_report_includes_webview_diagnostics_analytics_and_ignores_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="a",
            confidence=1.0,
            target=ResolvedTarget(
                ref="r",
                confidence=1.0,
                resolver_name="x",
                metadata={
                    "webview_switch_diagnostics": {
                        "status": "dry_run",
                        "recommended_context": "WEBVIEW_1",
                        "switch_required_future": True,
                        "switch_attempted": False,
                        "reason": "dom_detected",
                        "warnings": ["deferred"],
                        "raw_context_name": "SHOULD_NOT_COUNT",
                    }
                },
            ),
        )
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload["analytics"]["webview_diagnostics_summary"]
    assert summary["total_with_diagnostics"] == 1
    assert summary["status_counts"] == {"dry_run": 1}
    assert summary["recommended_context_counts"] == {"WEBVIEW_1": 1}
    assert summary["switch_required_future_count"] == 1
    assert summary["switch_attempted_count"] == 0
    assert summary["reason_counts"] == {"dom_detected": 1}
    assert summary["warning_counts"] == {"deferred": 1}

def test_json_report_preserves_and_redacts_webview_eligibility_and_context_selection(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap",
        confidence=0.9,
        target=ResolvedTarget(
            ref="r", confidence=0.9, resolver_name="x",
            metadata={
                "webview_switch_eligibility": {
                    "decision": "eligible", "reason": "opt_in_enabled", "instruction_hint_type": "web",
                    "opt_in_present": True, "diagnostics_candidate": True, "guardrails_allowed": True,
                    "webview_context_available": True, "multi_webview": False, "system_dialog_blocking": False,
                    "switch_attempted": False, "warnings": ["w1"], "evidence": ["e1"], "raw_xml": "<x/>",
                },
                "webview_context_selection": {
                    "decision": "selected", "reason": "single_candidate", "selection_policy": "first",
                    "selected_context_type": "WEBVIEW", "selected_context_index": 0, "candidate_context_count": 1,
                    "eligibility_decision": "eligible", "switch_attempted": False, "warnings": ["w2"], "evidence": ["e2"],
                    "raw_context_names": ["SECRET"],
                },
            }
        )
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]
    assert md["webview_switch_eligibility"]["decision"] == "eligible"
    assert "raw_xml" not in md["webview_switch_eligibility"]
    assert md["webview_context_selection"]["selection_policy"] == "first"
    assert "raw_context_names" not in md["webview_context_selection"]


def test_json_report_includes_webview_eligibility_and_context_selection_analytics(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(status="passed", action="a", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata={
            "webview_switch_eligibility": {"decision": "eligible", "reason": "r1", "instruction_hint_type": "web", "opt_in_present": True, "switch_attempted": False, "warnings": ["warn"], "raw_instruction": "x"},
            "webview_context_selection": {"decision": "selected", "reason": "r2", "selection_policy": "first", "selected_context_type": "WEBVIEW", "eligibility_decision": "eligible", "candidate_context_count": 2, "switch_attempted": False, "warnings": ["warn2"], "context_name": "SECRET"},
        }))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    es = payload["analytics"]["webview_switch_eligibility_summary"]
    cs = payload["analytics"]["webview_context_selection_summary"]
    assert es["total_with_eligibility"] == 1 and es["decision_counts"] == {"eligible": 1}
    assert es["warning_counts"] == {"warn": 1}
    assert cs["total_with_context_selection"] == 1 and cs["selection_policy_counts"] == {"first": 1}
    assert cs["candidate_context_count_buckets"] == {"0": 0, "1": 0, "2-3": 1, "4+": 0}

def test_json_report_preserves_and_redacts_webview_switch_execution(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(status="passed", action="a", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata={
            "webview_switch_execution": {
                "switch_enabled": True, "switch_attempted": True, "switch_status": "switched",
                "restore_attempted": True, "restore_status": "restored", "original_context_type": "native",
                "selected_context_type": "webview", "context_selection_reason": "single_candidate",
                "reason": "execution_ok", "evidence": ["e1"], "warnings": ["w1"], "safe_metadata_only": True,
                "raw_context_name": "SECRET", "exception_trace": "trace", "exception_message": "boom",
            }
        }))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert ws["switch_enabled"] is True
    assert ws["selected_context_type"] == "webview"
    assert "raw_context_name" not in ws
    assert "exception_trace" not in ws
    assert "exception_message" not in ws

def test_json_report_includes_webview_switch_execution_analytics_and_ignores_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(status="passed", action="a", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata={
            "webview_switch_execution": {
                "switch_enabled": True, "switch_attempted": True, "switch_status": "switched",
                "restore_attempted": True, "restore_status": "restored", "original_context_type": "native",
                "selected_context_type": "webview", "reason": "execution_ok", "warnings": ["deferred"],
                "raw_context_name": "SHOULD_NOT_COUNT",
            }
        }))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["total_with_switch_execution"] == 1
    assert summary["switch_enabled_count"] == 1
    assert summary["switch_attempted_count"] == 1
    assert summary["restore_attempted_count"] == 1
    assert summary["switch_status_counts"] == {"switched": 1}
    assert summary["restore_status_counts"] == {"restored": 1}
    assert summary["original_context_type_counts"] == {"native": 1}
    assert summary["selected_context_type_counts"] == {"webview": 1}
    assert summary["reason_counts"] == {"execution_ok": 1}
    assert summary["warning_counts"] == {"deferred": 1}

def test_json_report_preserves_safe_system_dialog_detection_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Allow",
        confidence=0.88,
        target=ResolvedTarget(
            ref='text="Allow"',
            confidence=0.88,
            resolver_name="x",
            metadata={
                "system_dialog_detection": {
                    "dialog_detected": True,
                    "dialog_type": "permission_prompt",
                    "platform": "android",
                    "owner": "system",
                    "recommended_action": "manual_review",
                    "confidence": 0.91,
                    "evidence": ["permission keyword"],
                    "warnings": ["metadata_only"],
                    "safe_metadata_only": True,
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sd = payload["results"][0]["target"]["metadata"]["system_dialog_detection"]
    assert sd["dialog_detected"] is True
    assert sd["dialog_type"] == "permission_prompt"
    assert sd["safe_metadata_only"] is True


def test_json_report_redacts_unsafe_system_dialog_detection_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="failed",
        action="Tap",
        confidence=0.2,
        target=ResolvedTarget(
            ref='text="Allow"',
            confidence=0.2,
            resolver_name="x",
            metadata={
                "system_dialog_detection": {
                    "dialog_detected": False,
                    "dialog_type": "none",
                    "raw_xml": "<x/>",
                    "hierarchy_xml": "<y/>",
                    "screenshot_bytes": "abc",
                    "provider_payload": {"token": "x"},
                    "raw_context_name": "WEBVIEW_com.x",
                    "package_name": "com.x",
                    "exception_trace": "trace",
                    "raw_instruction": "tap allow now",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sd = payload["results"][0]["target"]["metadata"]["system_dialog_detection"]
    assert "raw_xml" not in sd
    assert "hierarchy_xml" not in sd
    assert "screenshot_bytes" not in sd
    assert "provider_payload" not in sd
    assert "raw_context_name" not in sd
    assert "package_name" not in sd
    assert "exception_trace" not in sd
    assert "raw_instruction" not in sd


def test_json_report_includes_system_dialog_analytics_summary(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="A",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Allow"', confidence=0.9, resolver_name="x",
                metadata={"system_dialog_detection": {
                    "dialog_detected": True,
                    "dialog_type": "permission_prompt",
                    "platform": "android",
                    "owner": "system",
                    "recommended_action": "manual_review",
                    "confidence": 0.9,
                    "warnings": ["w1"],
                }}
            ),
        ),
        StepResult(status="failed", action="B", confidence=0.5),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ss = payload["analytics"]["system_dialog_summary"]
    assert ss["total_with_detection"] == 1
    assert ss["detected_count"] == 1
    assert ss["dialog_type_counts"]["permission_prompt"] == 1
    assert ss["warning_counts"]["w1"] == 1

def test_json_report_preserves_safe_system_dialog_guardrails_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="noop",
        confidence=1.0,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=1.0,
            resolver_name="x",
            metadata={
                "system_dialog_guardrails": {
                    "decision": "blocked",
                    "reason": "opt_in_missing",
                    "dialog_detected": True,
                    "dialog_type": "permission",
                    "requested_action": "allow",
                    "requires_opt_in": True,
                    "opt_in_present": False,
                    "action_attempted": False,
                    "recommended_action": "allow",
                    "evidence": ["dialog:permission"],
                    "warnings": [],
                    "safe_metadata_only": True,
                    "raw_xml": "<x/>",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["system_dialog_guardrails"]
    assert md["decision"] == "blocked"
    assert md["action_attempted"] is False
    assert "raw_xml" not in md


def test_json_report_redacts_explicit_unsafe_system_dialog_guardrails_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="noop",
        confidence=1.0,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=1.0,
            resolver_name="x",
            metadata={
                "system_dialog_guardrails": {
                    "decision": "allowed",
                    "reason": "policy_allows",
                    "dialog_detected": True,
                    "dialog_type": "permission",
                    "requested_action": "allow",
                    "recommended_action": "allow",
                    "raw_dom": "<dom/>",
                    "screenshot": "bytes",
                    "screenshot_bytes": "abc",
                    "page_source": "<xml/>",
                    "provider_payload": {"token": "x"},
                    "raw_context_name": "WEBVIEW_com.secret",
                    "package_name": "com.secret",
                    "process_name": "pid",
                    "exception_trace": "trace",
                    "raw_instruction": "tap allow now",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["system_dialog_guardrails"]
    for key in (
        "raw_dom", "screenshot", "screenshot_bytes", "page_source", "provider_payload",
        "raw_context_name", "package_name", "process_name", "exception_trace", "raw_instruction"
    ):
        assert key not in md


def test_json_report_includes_system_dialog_guardrails_analytics_summary_and_ignores_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="A",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Allow"', confidence=0.9, resolver_name="x",
                metadata={"system_dialog_guardrails": {
                    "decision": "blocked",
                    "reason": "opt_in_missing",
                    "dialog_detected": True,
                    "dialog_type": "permission",
                    "requested_action": "allow",
                    "opt_in_present": False,
                    "action_attempted": False,
                    "recommended_action": "allow",
                    "warnings": ["w1"],
                    "raw_instruction": "SECRET",
                }}
            ),
        ),
        StepResult(status="failed", action="B", confidence=0.5),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    gs = payload["analytics"]["system_dialog_guardrails_summary"]
    assert gs["total_with_guardrails"] == 1
    assert gs["decision_counts"]["blocked"] == 1
    assert gs["reason_counts"]["opt_in_missing"] == 1
    assert gs["dialog_type_counts"]["permission"] == 1
    assert gs["requested_action_counts"]["allow"] == 1
    assert gs["recommended_action_counts"]["allow"] == 1
    assert gs["opt_in_present_count"] == 0
    assert gs["action_attempted_count"] == 0
    assert gs["warning_counts"]["w1"] == 1
    assert "SECRET" not in json.dumps(gs)


def test_json_report_preserves_safe_system_dialog_action_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Allow",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Allow"',
            confidence=0.9,
            resolver_name="x",
            metadata={"system_dialog_action": {
                "action_requested": "allow",
                "candidate_found": True,
                "action_attempted": False,
                "action_status": "blocked",
                "reason": "opt_in_missing",
                "evidence": ["dialog:permission"],
                "warnings": ["metadata_only"],
                "safe_metadata_only": True,
            }},
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["system_dialog_action"]
    assert md["action_requested"] == "allow"
    assert md["candidate_found"] is True
    assert md["safe_metadata_only"] is True


def test_json_report_redacts_unsafe_system_dialog_action_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="failed",
        action="Tap",
        confidence=0.1,
        target=ResolvedTarget(
            ref='text="Allow"',
            confidence=0.1,
            resolver_name="x",
            metadata={"system_dialog_action": {
                "action_status": "error",
                "raw_xml": "<x/>",
                "hierarchy_xml": "<y/>",
                "raw_dom": "<dom/>",
                "screenshot_bytes": "abc",
                "provider_payload": {"token": "x"},
                "raw_context_name": "WEBVIEW_secret",
                "package_name": "com.secret",
                "process_name": "pid",
                "exception_trace": "trace",
                "raw_instruction": "tap allow now",
            }},
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["system_dialog_action"]
    for key in ("raw_xml", "hierarchy_xml", "raw_dom", "screenshot_bytes", "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace", "raw_instruction"):
        assert key not in md


def test_json_report_includes_system_dialog_action_analytics_summary_and_ignores_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="A",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Allow"', confidence=0.9, resolver_name="x",
                metadata={"system_dialog_action": {
                    "action_requested": "allow",
                    "candidate_found": True,
                    "action_attempted": True,
                    "action_status": "executed",
                    "reason": "explicit_opt_in",
                    "warnings": ["w1"],
                    "raw_instruction": "SECRET",
                }}
            ),
        ),
        StepResult(status="failed", action="B", confidence=0.4),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sm = payload["analytics"]["system_dialog_action_summary"]
    assert sm["total_with_action_metadata"] == 1
    assert sm["candidate_found_count"] == 1
    assert sm["action_attempted_count"] == 1
    assert sm["action_status_counts"]["executed"] == 1
    assert sm["reason_counts"]["explicit_opt_in"] == 1
    assert sm["warning_counts"]["w1"] == 1
    assert "SECRET" not in json.dumps(sm)

def test_json_report_sanitizes_scroll_discovery_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Continue",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Continue"',
            confidence=0.9,
            resolver_name="appium_hierarchy",
            metadata={
                "scroll_discovery": {
                    "scroll_needed": True,
                    "status": "candidate",
                    "reason": "target_not_visible",
                    "platform": "android",
                    "target_hint_type": "text",
                    "scroll_direction": "down",
                    "max_scrolls": 3,
                    "candidate_container_count": 1,
                    "evidence": ["target:not_visible"],
                    "warnings": [],
                    "safe_metadata_only": True,
                    "hierarchy_xml": "<raw/>",
                    "raw_instruction": "Tap Continue",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    md = payload["results"][0]["target"]["metadata"]["scroll_discovery"]
    assert md["scroll_needed"] is True
    assert "hierarchy_xml" not in md
    assert "raw_instruction" not in md

def test_json_report_includes_scroll_discovery_analytics_summary_and_ignores_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="Tap Continue",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Continue"',
                confidence=0.9,
                resolver_name="x",
                metadata={"scroll_discovery": {
                    "scroll_needed": True,
                    "status": "candidate",
                    "reason": "target_not_visible",
                    "platform": "android",
                    "target_hint_type": "text",
                    "scroll_direction": "down",
                    "max_scrolls": 3,
                    "candidate_container_count": 2,
                    "warnings": ["w1"],
                    "raw_xml": "SECRET",
                    "raw_instruction": "SECRET",
                }}
            ),
        ),
        StepResult(status="failed", action="B", confidence=0.4),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ss = payload["analytics"]["scroll_discovery_summary"]
    assert ss["total_with_scroll_discovery"] == 1
    assert ss["scroll_needed_count"] == 1
    assert ss["status_counts"]["candidate"] == 1
    assert ss["reason_counts"]["target_not_visible"] == 1
    assert ss["platform_counts"]["android"] == 1
    assert ss["target_hint_type_counts"]["text"] == 1
    assert ss["scroll_direction_counts"]["down"] == 1
    assert ss["warning_counts"]["w1"] == 1
    assert ss["max_scrolls_buckets"]["3-5"] == 1
    assert ss["candidate_container_count_buckets"]["2-3"] == 1
    assert "SECRET" not in json.dumps(ss)

def test_json_report_preserves_safe_scroll_resolution_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "scroll_resolution": {
                    "enabled": True,
                    "attempted": True,
                    "attempt_count": 2,
                    "max_scrolls": 5,
                    "found_after_scroll": True,
                    "final_status": "found",
                    "reason": "resolved_after_scroll",
                    "evidence": ["try1", "try2"],
                    "warnings": ["metadata_only"],
                    "safe_metadata_only": True,
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sr = payload["results"][0]["target"]["metadata"]["scroll_resolution"]
    assert sr["enabled"] is True
    assert sr["attempt_count"] == 2
    assert sr["final_status"] == "found"


def test_json_report_redacts_unsafe_scroll_resolution_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "scroll_resolution": {
                    "enabled": True,
                    "final_status": "not_found",
                    "raw_xml": "<x/>",
                    "screenshot": "abc",
                    "provider_payload": {"s": 1},
                    "raw_context_name": "WEBVIEW_secret",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sr = payload["results"][0]["target"]["metadata"]["scroll_resolution"]
    assert sr["enabled"] is True
    assert sr["final_status"] == "not_found"
    for k in ["raw_xml", "screenshot", "provider_payload", "raw_context_name"]:
        assert k not in sr


def test_json_report_scroll_resolution_analytics_and_unsafe_ignored(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(status="passed", action="a", confidence=1.0, target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x", metadata={"scroll_resolution": {"enabled": True, "attempted": True, "attempt_count": 2, "max_scrolls": 4, "found_after_scroll": True, "final_status": "found", "reason": "ok", "warnings": ["w1"], "raw_xml": "x"}})),
        StepResult(status="failed", action="b", confidence=0.2, target=ResolvedTarget(ref="r", confidence=0.2, resolver_name="x", metadata={"scroll_resolution": {"enabled": False, "attempted": False, "attempt_count": 0, "max_scrolls": 0, "found_after_scroll": False, "final_status": "not_found", "reason": "disabled", "warnings": ["w2"]}})),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    s = payload["analytics"]["scroll_resolution_summary"]
    assert s["total_with_scroll_resolution"] == 2
    assert s["enabled_count"] == 1
    assert s["attempted_count"] == 1
    assert s["found_after_scroll_count"] == 1
    assert s["final_status_counts"] == {"found": 1, "not_found": 1}
    assert s["reason_counts"] == {"ok": 1, "disabled": 1}
    assert s["warning_counts"] == {"w1": 1, "w2": 1}
    assert s["max_scrolls_buckets"] == {"0": 1, "1-2": 0, "3-5": 1, "6+": 0}
    assert s["attempt_count_buckets"] == {"0": 1, "1": 0, "2-3": 1, "4+": 0}

def test_json_report_repeated_region_diagnostics_redacts_unsafe_fields(tmp_path):
    out = tmp_path / "r.json"
    result = StepResult(
        status="passed",
        action="tap",
        confidence=1.0,
        target=ResolvedTarget(
            ref="r",
            confidence=1.0,
            resolver_name="x",
            metadata={
                "repeated_region_diagnostics": {
                    "status": "resolved",
                    "region_type": "row",
                    "matched_region_count": 1,
                    "candidate_count": 2,
                    "anchor_hint_type": "text",
                    "target_action_hint": "edit",
                    "reason": "same_region_anchor_match",
                    "evidence": ["ok"],
                    "warnings": [],
                    "safe_metadata_only": True,
                    "raw_xml": "SECRET",
                    "raw_instruction": "SECRET",
                }
            },
        ),
    )
    write_json_report([result], path=out)
    payload = json.loads(out.read_text())
    md = payload["results"][0]["target"]["metadata"]["repeated_region_diagnostics"]
    assert "raw_xml" not in md
    assert "raw_instruction" not in md
    assert md["status"] == "resolved"


def test_json_report_repeated_region_diagnostics_allowlists_safe_fields_only(tmp_path):
    out = tmp_path / "r.json"
    result = StepResult(
        status="passed",
        action="tap",
        confidence=1.0,
        target=ResolvedTarget(
            ref="r",
            confidence=1.0,
            resolver_name="x",
            metadata={"repeated_region_diagnostics": {
                "status": "resolved",
                "region_type": "row",
                "matched_region_count": 1,
                "candidate_count": 2,
                "anchor_hint_type": "text",
                "target_action_hint": "edit",
                "reason": "same_region_anchor_match",
                "evidence": ["ok"],
                "warnings": ["w"],
                "safe_metadata_only": True,
                "raw_xml": "x",
                "raw_anchor_text": "secret",
                "raw_candidate_text": "secret",
                "selected_candidate_ref": {"id": "too_detailed"},
            }},
        ),
    )
    write_json_report([result], path=out)
    md = json.loads(out.read_text())["results"][0]["target"]["metadata"]["repeated_region_diagnostics"]
    assert set(md.keys()) == {
        "status", "region_type", "matched_region_count", "candidate_count", "anchor_hint_type",
        "target_action_hint", "reason", "evidence", "warnings", "safe_metadata_only"
    }


def test_json_report_repeated_region_summary_counts_and_unsafe_ignored(tmp_path):
    out = tmp_path / "r.json"
    results = [
        StepResult(status="passed", action="a", confidence=1.0, target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x", metadata={"repeated_region_diagnostics": {"status": "resolved", "region_type": "card", "matched_region_count": 1, "candidate_count": 2, "anchor_hint_type": "text", "target_action_hint": "edit", "reason": "same_region_anchor_match", "warnings": ["w1"], "raw_xml": "secret"}})),
        StepResult(status="failed", action="b", confidence=0.2, target=ResolvedTarget(ref="r", confidence=0.2, resolver_name="x", metadata={"repeated_region_diagnostics": {"status": "no_anchor", "region_type": "list", "matched_region_count": 0, "candidate_count": 4, "anchor_hint_type": "none", "target_action_hint": "open", "reason": "anchor_missing", "warnings": ["w2"], "provider_payload": {"x":1}}})),
    ]
    write_json_report(results, path=out)
    summary = json.loads(out.read_text())["analytics"]["repeated_region_summary"]
    assert summary["total_with_repeated_region_diagnostics"] == 2
    assert summary["status_counts"] == {"resolved": 1, "no_anchor": 1}
    assert summary["region_type_counts"] == {"card": 1, "list": 1}
    assert summary["reason_counts"] == {"same_region_anchor_match": 1, "anchor_missing": 1}
    assert summary["anchor_hint_type_counts"] == {"text": 1, "none": 1}
    assert summary["target_action_hint_counts"] == {"edit": 1, "open": 1}
    assert summary["warning_counts"] == {"w1": 1, "w2": 1}
    assert summary["matched_region_count_buckets"] == {"0": 1, "1": 1, "2-3": 0, "4+": 0}
    assert summary["candidate_count_buckets"] == {"0": 0, "1": 0, "2-3": 1, "4+": 1}

def test_json_report_sanitizes_icon_detection_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap search",
        confidence=0.9,
        target=ResolvedTarget(
            ref='xpath=//icon',
            confidence=0.9,
            resolver_name="appium_hierarchy",
            metadata={
                "icon_detection": {
                    "status": "resolved",
                    "icon_hint_type": "content_desc",
                    "target_icon": "search",
                    "candidate_count": 2,
                    "matched_candidate_count": 1,
                    "reason": "content_desc_match",
                    "evidence": ["icon:search"],
                    "warnings": [],
                    "safe_metadata_only": True,
                    "raw_instruction": "tap search icon",
                    "raw_content_desc": "Search",
                    "raw_resource_id": "id/ic_search",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    icon = payload["results"][0]["target"]["metadata"]["icon_detection"]
    assert icon["status"] == "resolved"
    assert "raw_instruction" not in icon
    assert "raw_content_desc" not in icon
    assert "raw_resource_id" not in icon


def test_json_report_icon_detection_allowlists_safe_fields_only(tmp_path):
    out = tmp_path / "r.json"
    result = StepResult(
        status="passed",
        action="tap",
        confidence=1.0,
        target=ResolvedTarget(
            ref="r",
            confidence=1.0,
            resolver_name="x",
            metadata={"icon_detection": {
                "status": "resolved",
                "icon_hint_type": "content_desc",
                "target_icon": "search",
                "candidate_count": 2,
                "matched_candidate_count": 1,
                "reason": "content_desc_match",
                "evidence": ["ok"],
                "warnings": ["w"],
                "safe_metadata_only": True,
                "raw_xml": "secret",
                "page_source": "<xml/>",
                "provider_payload": {"s": 1},
            }},
        ),
    )
    write_json_report([result], path=out)
    icon = json.loads(out.read_text())["results"][0]["target"]["metadata"]["icon_detection"]
    assert set(icon.keys()) == {
        "status", "icon_hint_type", "target_icon", "candidate_count", "matched_candidate_count",
        "reason", "evidence", "warnings", "safe_metadata_only"
    }


def test_json_report_includes_icon_detection_summary_and_ignores_unsafe_keys(tmp_path):
    out = tmp_path / "r.json"
    results = [
        StepResult(status="passed", action="a", confidence=0.9, target=ResolvedTarget(ref="r1", confidence=0.9, resolver_name="x", metadata={"icon_detection": {"status": "resolved", "icon_hint_type": "content_desc", "target_icon": "search", "candidate_count": 2, "matched_candidate_count": 1, "reason": "content_desc_match", "warnings": ["w1"], "raw_xml": "secret"}})),
        StepResult(status="failed", action="b", confidence=0.2, target=ResolvedTarget(ref="r2", confidence=0.2, resolver_name="x", metadata={"icon_detection": {"status": "no_match", "icon_hint_type": "resource_id", "target_icon": "menu", "candidate_count": 4, "matched_candidate_count": 0, "reason": "no_icon_match", "warnings": ["w2"], "provider_payload": {"x": 1}}})),
    ]
    write_json_report(results, path=out)
    summary = json.loads(out.read_text())["analytics"]["icon_detection_summary"]
    assert summary["total_with_icon_detection"] == 2
    assert summary["status_counts"] == {"resolved": 1, "no_match": 1}
    assert summary["icon_hint_type_counts"] == {"content_desc": 1, "resource_id": 1}
    assert summary["target_icon_counts"] == {"search": 1, "menu": 1}
    assert summary["reason_counts"] == {"content_desc_match": 1, "no_icon_match": 1}
    assert summary["warning_counts"] == {"w1": 1, "w2": 1}
    assert summary["candidate_count_buckets"] == {"0": 0, "1": 0, "2-3": 1, "4+": 1}
    assert summary["matched_candidate_count_buckets"] == {"0": 1, "1": 1, "2-3": 0, "4+": 0}

def test_json_report_preserves_safe_mobile_memory_signature_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Login",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="memory_cache",
            metadata={
                "mobile_memory_signature": {
                    "enabled": True,
                    "platform": "android",
                    "surface_type": "hybrid",
                    "context_mode": "hybrid",
                    "dialog_state": "none",
                    "scroll_state": "candidate",
                    "repeated_region_status": "resolved",
                    "icon_target": "search",
                    "signature_parts": ["platform:android", "surface:hybrid"],
                    "warnings": ["metadata_only"],
                    "safe_metadata_only": True,
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sig = payload["results"][0]["target"]["metadata"]["mobile_memory_signature"]
    assert sig["platform"] == "android"
    assert sig["signature_parts"] == ["platform:android", "surface:hybrid"]


def test_json_report_redacts_unsafe_mobile_memory_signature_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap Login",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="memory_cache",
            metadata={
                "mobile_memory_signature": {
                    "platform": "android",
                    "surface_type": "android_native",
                    "raw_xml": "<root/>",
                    "provider_payload": {"secret": 1},
                    "raw_resource_id": "id",
                    "credentials": "abc",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    sig = payload["results"][0]["target"]["metadata"]["mobile_memory_signature"]
    assert sig["platform"] == "android"
    assert "raw_xml" not in sig
    assert "provider_payload" not in sig
    assert "raw_resource_id" not in sig
    assert "credentials" not in sig


def test_json_report_includes_mobile_memory_signature_analytics_summary(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="passed",
            action="Tap",
            confidence=0.9,
            target=ResolvedTarget(
                ref="r",
                confidence=0.9,
                resolver_name="x",
                metadata={"mobile_memory_signature": {
                    "platform": "android",
                    "surface_type": "hybrid",
                    "context_mode": "hybrid",
                    "dialog_state": "none",
                    "scroll_state": "candidate",
                    "repeated_region_status": "resolved",
                    "icon_target": "search",
                    "warnings": ["metadata_only", "candidate"],
                    "raw_xml": "<unsafe/>",
                }},
            ),
        ),
        StepResult(status="failed", action="Noop", confidence=0.1),
    ]

    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload["analytics"]["mobile_memory_signature_summary"]
    assert summary["total_with_mobile_memory_signature"] == 1
    assert summary["platform_counts"] == {"android": 1}
    assert summary["surface_type_counts"] == {"hybrid": 1}
    assert summary["warning_counts"]["metadata_only"] == 1
    assert "raw_xml" not in summary["warning_counts"]

def test_json_report_cloud_provider_summary_safe_and_redacted(tmp_path):
    out = tmp_path / 'report.json'
    result = StepResult(
        status='passed', action='cloud', confidence=0.9,
        target=ResolvedTarget(ref='x', confidence=0.9, resolver_name='r', metadata={
            'cloud_provider_summary': {
                'provider': 'browserstack', 'provider_namespace': 'bstack:options', 'platform': 'android',
                'device_name_present': True, 'app_launch_strategy': 'app_id', 'url_source': 'cloud_appium_url',
                'automation_name': 'UiAutomator2', 'session_name_present': True, 'build_name_present': False,
                'safe_metadata_only': True, 'warnings': ['ok'], 'username': 'u', 'raw_url': 'https://u:p@host',
                'raw_capabilities': {'x': 'y'},
            }
        })
    )
    write_json_report([result], path=out)
    payload = json.loads(out.read_text())
    md = payload['results'][0]['target']['metadata']['cloud_provider_summary']
    assert md['provider'] == 'browserstack'
    assert 'username' not in md and 'raw_url' not in md and 'raw_capabilities' not in md
    summary = payload['analytics']['cloud_provider_summary']
    assert summary['total_with_cloud_provider_summary'] == 1
    assert summary['provider_counts']['browserstack'] == 1


def test_json_report_cloud_provider_unsafe_keys_do_not_affect_analytics(tmp_path):
    out = tmp_path / 'report.json'
    result = StepResult(status='passed', action='cloud', confidence=0.9,
        target=ResolvedTarget(ref='x', confidence=0.9, resolver_name='r', metadata={
            'cloud_provider_summary': {'username': 'u', 'token': 't', 'raw_url': 'x'}
        }))
    write_json_report([result], path=out)
    summary = json.loads(out.read_text())['analytics']['cloud_provider_summary']
    assert summary['total_with_cloud_provider_summary'] == 0

def test_json_report_preserves_safe_webview_switch_wiring_plan_metadata(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "webview_switch_wiring_plan": {
                    "enabled": True,
                    "reason": "enabled",
                    "operation_type": "execute",
                    "mode": "opt_in",
                    "eligibility_decision": "allowed",
                    "context_selection_decision": "selected",
                    "switch_ready": True,
                    "safe_metadata_only": True,
                    "warnings": ["w1"],
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    md = json.loads(report_path.read_text(encoding="utf-8"))["results"][0]["target"]["metadata"]
    plan = md["webview_switch_wiring_plan"]
    assert plan["enabled"] is True
    assert plan["switch_ready"] is True
    assert plan["reason"] == "enabled"


def test_json_report_redacts_unsafe_webview_switch_wiring_plan_metadata_and_analytics(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    result = StepResult(
        status="passed",
        action="Tap",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="x",
            metadata={
                "webview_switch_wiring_plan": {
                    "enabled": True,
                    "reason": "enabled",
                    "operation_type": "execute",
                    "mode": "opt_in",
                    "eligibility_decision": "allowed",
                    "context_selection_decision": "selected",
                    "switch_ready": True,
                    "warnings": ["kept"],
                    "raw_context_name": "WEBVIEW_secret",
                    "context_names": ["WEBVIEW_secret"],
                    "exception_message": "boom",
                }
            },
        ),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    plan = payload["results"][0]["target"]["metadata"]["webview_switch_wiring_plan"]
    assert "raw_context_name" not in plan
    assert "context_names" not in plan
    assert "exception_message" not in plan
    summary = payload["analytics"]["webview_switch_wiring_plan_summary"]
    assert summary["total_with_wiring_plan"] == 1
    assert summary["enabled_count"] == 1
    assert summary["switch_ready_count"] == 1
    assert summary["reason_counts"] == {"enabled": 1}
    assert "WEBVIEW_secret" not in str(summary)


def test_json_report_accepts_adapter_skeleton_wiring_plan_validate_extract(tmp_path):
    cfg = BubblegumConfig(
        webview_switching=WebviewSwitchingConfig(
            enable_webview_switching=True,
            webview_switching_mode="opt_in",
            webview_switch_allowed_operations=["verify", "extract"],
        )
    )
    adapter = AppiumAdapter(_Driver())
    adapter._config = cfg

    validate_plan = adapter._prepare_webview_switch_metadata_for_operation(
        operation_type="validate",
        instruction="Login",
        target_metadata={
            "webview_switch_eligibility": {"decision": "allowed"},
            "webview_context_selection": {"decision": "selected", "selected_context_type": "webview"},
        },
        config=cfg,
    )["webview_switch_wiring_plan"]
    extract_plan = adapter._prepare_webview_switch_metadata_for_operation(
        operation_type="extract",
        instruction=None,
        target_metadata={
            "webview_switch_eligibility": {"decision": "allowed"},
            "webview_context_selection": {"decision": "selected", "selected_context_type": "webview"},
        },
        config=cfg,
    )["webview_switch_wiring_plan"]

    report_path = tmp_path / "bubblegum_report.json"
    write_json_report(
        [
            StepResult(status="passed", action="Validate", confidence=1, target=ResolvedTarget(ref="a", confidence=1, resolver_name="x", metadata={"webview_switch_wiring_plan": validate_plan})),
            StepResult(status="passed", action="Extract", confidence=1, target=ResolvedTarget(ref="b", confidence=1, resolver_name="x", metadata={"webview_switch_wiring_plan": extract_plan})),
        ],
        path=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload["analytics"]["webview_switch_wiring_plan_summary"]
    assert summary["operation_type_counts"] == {"validate": 1, "extract": 1}
    assert payload["results"][0]["target"]["metadata"]["webview_switch_wiring_plan"]["operation_type"] == "validate"
    assert payload["results"][1]["target"]["metadata"]["webview_switch_wiring_plan"]["operation_type"] == "extract"


def test_json_report_fake_wiring_extract_metadata_roundtrip(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    metadata = _build_fake_wiring_execution_metadata_for_extract()
    result = StepResult(status="passed", action="extract", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata=metadata))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert ws["switch_attempted"] is True
    assert ws["restore_attempted"] is True
    assert ws["switch_status"] == "switched"
    assert ws["restore_status"] == "restored"
    assert "selected_context" not in ws
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["switch_status_counts"] == {"switched": 1}
    assert summary["restore_status_counts"] == {"restored": 1}


def test_json_report_fake_wiring_validate_metadata_roundtrip(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    metadata = _build_fake_wiring_execution_metadata_for_validate()
    result = StepResult(status="passed", action="validate", confidence=1.0, target=ResolvedTarget(
        ref="r", confidence=1.0, resolver_name="x", metadata=metadata))
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert ws["switch_enabled"] is True
    assert ws["switch_attempted"] is True
    assert ws["restore_attempted"] is True
    assert ws["safe_metadata_only"] is True


def test_json_report_fake_wiring_failure_analytics_and_redaction(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    metadata = {
        "webview_switch_execution": {
            "switch_enabled": True,
            "switch_attempted": True,
            "switch_status": "failed",
            "restore_attempted": True,
            "restore_status": "failed",
            "reason": "execution_error",
            "warnings": ["switch_failed", "restore_failed", "WEBVIEW_secret_should_not_survive"],
            "raw_exception": "WEBVIEW_secret exploded",
            "safe_metadata_only": True,
        }
    }
    result = StepResult(
        status="failed",
        action="validate",
        confidence=1.0,
        target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x", metadata=metadata),
    )
    write_json_report([result], path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert "raw_exception" not in ws
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["switch_status_counts"]["failed"] == 1
    assert summary["restore_status_counts"]["failed"] == 1
    assert summary["warning_counts"]["switch_failed"] == 1
    assert summary["warning_counts"]["restore_failed"] == 1


def test_json_report_real_helper_metadata_sanitizes_context_names_and_exception_text(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    metadata = {
        "webview_switch_execution": {
            "switch_enabled": True,
            "switch_attempted": True,
            "switch_status": "failed",
            "restore_attempted": True,
            "restore_status": "failed",
            "original_context_type": "native",
            "selected_context_type": "webview",
            "reason": "execution_error",
            "warnings": ["switch_failed", "restore_failed"],
            "evidence": ["real_driver_helper"],
            "safe_metadata_only": True,
            "raw_context_name": "WEBVIEW_secret",
            "original_context_name": "NATIVE_APP secret",
            "exception_message": "switch failed WEBVIEW_secret",
            "raw_exception": "restore failed NATIVE_APP secret",
        }
    }
    write_json_report(
        [StepResult(status="failed", action="validate", confidence=1.0, target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x", metadata=metadata))],
        path=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    ws = payload["results"][0]["target"]["metadata"]["webview_switch_execution"]
    assert ws["switch_enabled"] is True
    assert ws["switch_status"] == "failed"
    assert ws["restore_status"] == "failed"
    assert "raw_context_name" not in ws
    assert "original_context_name" not in ws
    assert "exception_message" not in ws
    assert "raw_exception" not in ws
    assert "WEBVIEW_secret" not in str(ws)
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["switch_status_counts"]["failed"] == 1
    assert summary["restore_status_counts"]["failed"] == 1


def test_json_report_real_helper_blocked_metadata_is_reported_safely(tmp_path):
    report_path = tmp_path / "bubblegum_report.json"
    results = [
        StepResult(
            status="failed",
            action="validate",
            confidence=1.0,
            target=ResolvedTarget(
                ref="missing-ref",
                confidence=1.0,
                resolver_name="x",
                metadata={"webview_switch_execution": {
                    "switch_enabled": True,
                    "switch_attempted": False,
                    "switch_status": "blocked",
                    "restore_attempted": False,
                    "restore_status": "not_needed",
                    "reason": "internal_context_ref_missing",
                    "warnings": ["internal_context_ref_missing"],
                    "safe_metadata_only": True,
                    "raw_context_name": "WEBVIEW_should_not_leak",
                }},
            ),
        ),
        StepResult(
            status="failed",
            action="extract",
            confidence=1.0,
            target=ResolvedTarget(
                ref="opt-in",
                confidence=1.0,
                resolver_name="x",
                metadata={"webview_switch_execution": {
                    "switch_enabled": False,
                    "switch_attempted": False,
                    "switch_status": "blocked",
                    "restore_attempted": False,
                    "restore_status": "not_needed",
                    "reason": "opt_in_required",
                    "warnings": ["opt_in_required"],
                    "safe_metadata_only": True,
                }},
            ),
        ),
    ]
    write_json_report(results, path=report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    combined = str(payload)
    assert "WEBVIEW_should_not_leak" not in combined
    summary = payload["analytics"]["webview_switch_execution_summary"]
    assert summary["switch_status_counts"]["blocked"] == 2
    assert summary["restore_status_counts"]["not_needed"] == 2
    assert summary["reason_counts"]["internal_context_ref_missing"] == 1
    assert summary["reason_counts"]["opt_in_required"] == 1

def test_json_report_preserves_and_redacts_webview_readiness_diagnostics(tmp_path):
    out = tmp_path / "report.json"
    result = StepResult(status="passed", action="Tap", confidence=0.9, target=ResolvedTarget(ref='id="x"', confidence=0.9, resolver_name="x", metadata={
        "webview_readiness_diagnostics": {
            "enabled": True,
            "status": "waiting_for_target",
            "reason": "switch_ready_target_pending",
            "operation_type": "validate",
            "context_refresh_attempts": 1,
            "target_wait_attempted": False,
            "timeout_ms": 3000,
            "poll_interval_ms": 250,
            "max_context_refresh_attempts": 2,
            "evidence": ["x"],
            "warnings": ["w"],
            "safe_metadata_only": True,
            "raw_context_name": "SECRET",
            "exception_message": "SECRET_ERR",
        }
    }))
    write_json_report([result], path=out)
    md = json.loads(out.read_text(encoding="utf-8"))["results"][0]["target"]["metadata"]["webview_readiness_diagnostics"]
    assert md["status"] == "waiting_for_target"
    assert md["timeout_ms"] == 3000
    assert "raw_context_name" not in md
    assert "exception_message" not in md


def test_json_report_includes_webview_readiness_summary_and_ignores_unsafe_keys(tmp_path):
    out = tmp_path / "report.json"
    results = [
        StepResult(status="passed", action="A", confidence=0.9, target=ResolvedTarget(ref="a", confidence=0.9, resolver_name="x", metadata={"webview_readiness_diagnostics": {"enabled": True, "status": "context_available", "reason": "selected_context_available", "operation_type": "extract", "target_wait_attempted": True, "timeout_ms": 500, "poll_interval_ms": 200, "context_refresh_attempts": 0, "max_context_refresh_attempts": 1, "warnings": ["w1"], "raw_exception": "leak"}})),
        StepResult(status="failed", action="B", confidence=0.4, target=ResolvedTarget(ref="b", confidence=0.4, resolver_name="x", metadata={"webview_readiness_diagnostics": {"enabled": False, "status": "not_checked", "reason": "disabled", "operation_type": "validate", "target_wait_attempted": False, "timeout_ms": 3500, "poll_interval_ms": 600, "context_refresh_attempts": 2, "max_context_refresh_attempts": 3}})),
    ]
    write_json_report(results, path=out)
    summary = json.loads(out.read_text(encoding="utf-8"))["analytics"]["webview_readiness_summary"]
    assert summary["total_with_readiness"] == 2
    assert summary["enabled_count"] == 1
    assert summary["target_wait_attempted_count"] == 1
    assert summary["status_counts"]["context_available"] == 1
    assert summary["reason_counts"]["selected_context_available"] == 1
    assert summary["operation_type_counts"]["extract"] == 1
    assert summary["warning_counts"]["w1"] == 1
