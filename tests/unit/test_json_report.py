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
