from __future__ import annotations

import json
from pathlib import Path

from bubblegum.core.schemas import ArtifactRef, ErrorInfo, ResolvedTarget, StepResult
from bubblegum.reporting.allure_report import write_allure_results


def _result_files(out_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(out_dir.glob("*-result.json"))]


def _passed(action="Click Login", resolver="exact_text", conf=0.91) -> StepResult:
    target = ResolvedTarget(ref="role=button", confidence=conf, resolver_name=resolver)
    return StepResult(status="passed", action=action, target=target, confidence=conf, duration_ms=20)


def _failed(action="Submit") -> StepResult:
    error = ErrorInfo(error_type="ValidationFailedError", message="expected X got Y", resolver_name="fuzzy_text")
    return StepResult(status="failed", action=action, confidence=0.2, duration_ms=15, error=error)


def _recovered(action="Click Login") -> StepResult:
    target = ResolvedTarget(
        ref="role=button",
        confidence=0.78,
        resolver_name="fuzzy_text",
        metadata={
            "healing": {
                "applied": True,
                "requested": "Login",
                "matched": "Log In",
                "resolver": "fuzzy_text",
                "match_kind": "fuzzy",
                "similarity": 0.86,
                "severity": "review",
            }
        },
    )
    return StepResult(status="recovered", action=action, target=target, confidence=0.78, duration_ms=30)


# ---------------------------------------------------------------------------
# Files + status mapping
# ---------------------------------------------------------------------------


def test_writes_one_result_file_per_step(tmp_path):
    out = write_allure_results([_passed(), _failed()], output_dir=tmp_path / "allure-results")
    assert out == (tmp_path / "allure-results").resolve()
    results = _result_files(out)
    assert len(results) == 2
    # Every result is valid and finished.
    assert all(r["stage"] == "finished" for r in results)
    assert all(r["uuid"] for r in results)


def test_status_mapping(tmp_path):
    out_dir = tmp_path / "allure-results"
    results = [
        _passed(action="P"),
        _recovered(action="R"),
        _failed(action="F"),
        StepResult(status="skipped", action="S", duration_ms=0),
        StepResult(status="dry_run", action="D", duration_ms=0),
    ]
    write_allure_results(results, output_dir=out_dir)
    by_name = {r["name"]: r for r in _result_files(out_dir)}
    assert by_name["P"]["status"] == "passed"
    assert by_name["R"]["status"] == "passed"      # recovered does not fail the build
    assert by_name["F"]["status"] == "failed"
    assert by_name["S"]["status"] == "skipped"
    assert by_name["D"]["status"] == "skipped"


# ---------------------------------------------------------------------------
# Parameters, status details, steps
# ---------------------------------------------------------------------------


def test_parameters_include_resolver_and_confidence(tmp_path):
    out_dir = tmp_path / "allure-results"
    write_allure_results([_passed(resolver="exact_text", conf=0.91)], output_dir=out_dir)
    params = {p["name"]: p["value"] for p in _result_files(out_dir)[0]["parameters"]}
    assert params["resolver"] == "exact_text"
    assert params["confidence"] == "0.91"


def test_failed_result_has_status_details(tmp_path):
    out_dir = tmp_path / "allure-results"
    write_allure_results([_failed()], output_dir=out_dir)
    result = _result_files(out_dir)[0]
    assert result["statusDetails"]["message"] == "expected X got Y"
    assert "fuzzy_text" in result["statusDetails"]["trace"]


def test_recovered_result_surfaces_healing_step(tmp_path):
    out_dir = tmp_path / "allure-results"
    write_allure_results([_recovered()], output_dir=out_dir)
    result = _result_files(out_dir)[0]
    step_names = [s["name"] for s in result["steps"]]
    assert any("Self-healing" in n for n in step_names)
    heal_step = next(s for s in result["steps"] if "Self-healing" in s["name"])
    assert "'Login'" in heal_step["name"] and "'Log In'" in heal_step["name"]
    assert heal_step["status"] == "passed"


def test_soft_failure_tagged_in_parameters(tmp_path):
    out_dir = tmp_path / "allure-results"
    target = ResolvedTarget(ref="r", confidence=0.3, resolver_name="x", metadata={"soft": True})
    result = StepResult(status="failed", action="Check total", target=target, confidence=0.3,
                        error=ErrorInfo(error_type="ValidationFailedError", message="no"))
    write_allure_results([result], output_dir=out_dir)
    params = {p["name"]: p["value"] for p in _result_files(out_dir)[0]["parameters"]}
    assert params.get("soft") == "true"


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def test_screenshot_artifacts_copied_and_referenced(tmp_path):
    # A real screenshot file on disk that should be copied into the results dir.
    shot = tmp_path / "step1.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    artifact = ArtifactRef(type="screenshot", path=str(shot), timestamp="2026-05-04T00:00:00+00:00")
    result = StepResult(status="passed", action="Click", confidence=1.0, artifacts=[artifact],
                        target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x"))

    out_dir = tmp_path / "allure-results"
    write_allure_results([result], output_dir=out_dir)
    payload = _result_files(out_dir)[0]
    assert len(payload["attachments"]) == 1
    att = payload["attachments"][0]
    assert att["type"] == "image/png"
    # The referenced source file must exist inside the results dir.
    copied = out_dir / att["source"]
    assert copied.is_file()
    assert copied.read_bytes() == b"\x89PNG\r\n\x1a\nFAKE"


def test_missing_screenshot_file_is_skipped_gracefully(tmp_path):
    artifact = ArtifactRef(type="screenshot", path=str(tmp_path / "nope.png"), timestamp="2026-05-04T00:00:00+00:00")
    result = StepResult(status="passed", action="Click", confidence=1.0, artifacts=[artifact],
                        target=ResolvedTarget(ref="r", confidence=1.0, resolver_name="x"))
    out_dir = tmp_path / "allure-results"
    write_allure_results([result], output_dir=out_dir)
    assert _result_files(out_dir)[0]["attachments"] == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_results_creates_empty_dir(tmp_path):
    out_dir = tmp_path / "allure-results"
    out = write_allure_results([], output_dir=out_dir)
    assert out.is_dir()
    assert list(out.glob("*-result.json")) == []
