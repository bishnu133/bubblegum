from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.json_report import write_json_report


def test_html_wait_section_renders_only_when_present(tmp_path):
    with_wait = StepResult(
        status="passed",
        action="Click",
        confidence=1.0,
        target=ResolvedTarget(ref="x", confidence=1.0, resolver_name="r", metadata={
            "wait_used": True,
            "wait_mode": "visible",
            "wait_outcome": "success",
            "wait_adapter": "playwright",
            "wait_duration_ms": 12,
        }),
    )
    no_wait = StepResult(status="passed", action="No wait", confidence=1.0)
    out = write_html_report([with_wait, no_wait], path=tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    assert "Wait" in html
    assert "Mode:" in html


def test_reporting_redacts_unsafe_wait_fields(tmp_path):
    result = StepResult(
        status="failed",
        action="Click",
        confidence=0.1,
        target=ResolvedTarget(ref="x", confidence=0.1, resolver_name="r", metadata={
            "wait_used": True,
            "wait_mode": "visible",
            "wait_outcome": "failed",
            "wait_adapter": "appium",
            "wait_stack": "Traceback",
            "wait_payload": "secret",
        }),
    )
    json_path = write_json_report([result], path=tmp_path / "r.json")
    md = __import__("json").loads(json_path.read_text())["results"][0]["target"]["metadata"]
    assert "wait_stack" not in md
    assert "wait_payload" not in md
    html_path = write_html_report([result], path=tmp_path / "r.html")
    html = html_path.read_text(encoding="utf-8")
    assert "wait_stack" not in html
    assert "wait_payload" not in html
