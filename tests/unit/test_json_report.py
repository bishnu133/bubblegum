from __future__ import annotations

import json

from bubblegum.core.schemas import ArtifactRef, ErrorInfo, ResolvedTarget, ResolverTrace, StepResult
from bubblegum.reporting.html_report import build_report_analytics
from bubblegum.reporting.json_report import write_json_report


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
