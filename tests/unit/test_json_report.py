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
