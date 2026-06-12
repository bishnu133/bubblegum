from __future__ import annotations

from xml.etree import ElementTree as ET

from bubblegum.core.schemas import ArtifactRef, ErrorInfo, ResolvedTarget, ResolverTrace, StepResult
from bubblegum.reporting.junit_report import build_junit_tree, write_junit_report


def _recovered_result() -> StepResult:
    target = ResolvedTarget(
        ref='role=button[name="Log In"]',
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
                "message": "Resolved a near-match",
            }
        },
    )
    artifact = ArtifactRef(type="screenshot", path="artifacts/step1.png", timestamp="2026-05-04T00:00:00+00:00")
    trace = ResolverTrace(resolver_name="fuzzy_text", duration_ms=12, candidates=[target], can_run=True)
    return StepResult(
        status="recovered",
        action="Click Login",
        target=target,
        confidence=0.78,
        artifacts=[artifact],
        duration_ms=55,
        traces=[trace],
    )


def _failed_result() -> StepResult:
    error = ErrorInfo(
        error_type="ResolutionFailedError",
        message="No resolver found a candidate",
        resolver_name="exact_text",
    )
    return StepResult(status="failed", action="Submit order", confidence=0.2, duration_ms=30, error=error)


# ---------------------------------------------------------------------------
# Structure / well-formedness
# ---------------------------------------------------------------------------


def test_write_junit_report_creates_wellformed_file(tmp_path):
    report_path = tmp_path / "junit.xml"
    out = write_junit_report([_recovered_result(), _failed_result()], path=report_path)

    assert out == report_path.resolve()
    # Parses as valid XML and has the standard JUnit root.
    tree = ET.parse(report_path)
    root = tree.getroot()
    assert root.tag == "testsuites"
    suite = root.find("testsuite")
    assert suite is not None
    assert len(suite.findall("testcase")) == 2


def test_suite_level_counts_are_correct(tmp_path):
    results = [
        _recovered_result(),            # pass
        StepResult(status="passed", action="A", duration_ms=10),
        _failed_result(),               # failure
        StepResult(status="skipped", action="B", duration_ms=0),
        StepResult(status="dry_run", action="C", duration_ms=0),
    ]
    tree = build_junit_tree(results)
    root = tree.getroot()
    suite = root.find("testsuite")

    assert root.attrib["tests"] == "5"
    assert suite.attrib["tests"] == "5"
    assert suite.attrib["failures"] == "1"
    # skipped + dry_run both count as skipped
    assert suite.attrib["skipped"] == "2"
    assert suite.attrib["errors"] == "0"


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


def test_passed_step_has_no_failure_or_skipped(tmp_path):
    tree = build_junit_tree([StepResult(status="passed", action="Open page", duration_ms=5)])
    case = tree.getroot().find("testsuite/testcase")
    assert case.attrib["name"] == "Open page"
    assert case.find("failure") is None
    assert case.find("skipped") is None


def test_failed_step_emits_failure_element(tmp_path):
    tree = build_junit_tree([_failed_result()])
    case = tree.getroot().find("testsuite/testcase")
    failure = case.find("failure")
    assert failure is not None
    assert failure.attrib["type"] == "ResolutionFailedError"
    assert "No resolver found a candidate" in failure.attrib["message"]
    assert "exact_text" in (failure.text or "")


def test_skipped_and_dry_run_emit_skipped_element(tmp_path):
    tree = build_junit_tree(
        [
            StepResult(status="skipped", action="Skip me", duration_ms=0),
            StepResult(status="dry_run", action="Preview only", duration_ms=0),
        ]
    )
    cases = tree.getroot().findall("testsuite/testcase")
    skipped_case, dry_run_case = cases
    assert skipped_case.find("skipped") is not None
    dry = dry_run_case.find("skipped")
    assert dry is not None
    assert "dry-run" in dry.attrib["message"]


def test_recovered_step_passes_and_surfaces_heal_in_system_out(tmp_path):
    tree = build_junit_tree([_recovered_result()])
    case = tree.getroot().find("testsuite/testcase")
    # Recovered must NOT fail the build.
    assert case.find("failure") is None
    assert case.find("skipped") is None
    system_out = case.find("system-out")
    assert system_out is not None
    assert "Self-healing applied" in system_out.text
    assert "Login" in system_out.text and "Log In" in system_out.text


# ---------------------------------------------------------------------------
# Timing + artifacts
# ---------------------------------------------------------------------------


def test_durations_are_seconds_and_summed(tmp_path):
    results = [
        StepResult(status="passed", action="A", duration_ms=55),
        StepResult(status="passed", action="B", duration_ms=200),
    ]
    tree = build_junit_tree(results)
    root = tree.getroot()
    suite = root.find("testsuite")
    assert suite.attrib["time"] == "0.255"
    cases = suite.findall("testcase")
    assert cases[0].attrib["time"] == "0.055"
    assert cases[1].attrib["time"] == "0.200"


def test_artifact_paths_attached_as_properties(tmp_path):
    tree = build_junit_tree([_recovered_result()])
    case = tree.getroot().find("testsuite/testcase")
    props = case.find("properties")
    assert props is not None
    values = [p.attrib["value"] for p in props.findall("property")]
    assert "artifacts/step1.png" in values


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_results_produces_valid_empty_suite(tmp_path):
    report_path = tmp_path / "junit.xml"
    write_junit_report([], path=report_path)
    root = ET.parse(report_path).getroot()
    assert root.attrib["tests"] == "0"
    assert root.attrib["failures"] == "0"
    assert root.find("testsuite").findall("testcase") == []


def test_special_characters_are_escaped(tmp_path):
    report_path = tmp_path / "junit.xml"
    error = ErrorInfo(error_type="AssertionError", message='Expected <b> & "quoted"')
    result = StepResult(status="failed", action='Click "Save" & exit <now>', confidence=0.1, error=error)
    # Must round-trip through a real XML parse without raising.
    write_junit_report([result], path=report_path)
    case = ET.parse(report_path).getroot().find("testsuite/testcase")
    assert case.attrib["name"] == 'Click "Save" & exit <now>'
    assert '&' in case.find("failure").attrib["message"]
