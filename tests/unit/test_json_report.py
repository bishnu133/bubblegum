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
