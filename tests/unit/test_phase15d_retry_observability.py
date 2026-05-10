from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report


def test_html_report_renders_retry_section_when_present(tmp_path):
    path = tmp_path / "report.html"
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
    write_html_report([result], path=path)
    html = path.read_text(encoding="utf-8")
    assert "Retry" in html
    assert "Attempts:" in html
    assert "playwright" in html


def test_html_report_hides_retry_section_when_absent(tmp_path):
    path = tmp_path / "report.html"
    result = StepResult(status="passed", action="Click", confidence=1.0)
    write_html_report([result], path=path)
    html = path.read_text(encoding="utf-8")
    assert "<summary style=\"cursor:pointer;font-size:0.8rem;color:#64748b;\">Retry</summary>" not in html


def test_html_report_does_not_render_unsafe_retry_fields(tmp_path):
    path = tmp_path / "report.html"
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
                "retry_stack": "Traceback (most recent call last): ...",
                "retry_payload": "secret_body",
            },
        ),
    )
    write_html_report([result], path=path)
    html = path.read_text(encoding="utf-8")
    assert "retry_stack" not in html
    assert "secret_body" not in html
