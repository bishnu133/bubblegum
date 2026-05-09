from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import write_html_report


def test_html_report_renders_hydration_section_when_present(tmp_path):
    report_path = tmp_path / "report.html"
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
    write_html_report([StepResult(status="passed", action="Click Login", target=target, confidence=0.9)], path=report_path)
    body = report_path.read_text(encoding="utf-8")
    assert "Hydration diagnostics" in body
    assert "hydrated_text_ref" in body


def test_html_report_hides_hydration_section_when_absent(tmp_path):
    report_path = tmp_path / "report.html"
    target = ResolvedTarget(ref='text="Login"', confidence=0.9, resolver_name="exact_text", metadata={"foo": "bar"})
    write_html_report([StepResult(status="passed", action="Click Login", target=target, confidence=0.9)], path=report_path)
    body = report_path.read_text(encoding="utf-8")
    assert "Hydration diagnostics" not in body


def test_html_report_escapes_and_redacts_hydration_values(tmp_path):
    report_path = tmp_path / "report.html"
    target = ResolvedTarget(
        ref='text="Login"',
        confidence=0.9,
        resolver_name="vision_model",
        metadata={
            "hydration_status": "not_hydrated",
            "hydration_reason": "<script>alert(1)</script>",
            "match_count": 0,
            "hierarchy_xml": "<root secret='1'/>",
            "screenshot_bytes": "abc",
            "base64": "zzz",
            "raw_payload": "token",
            "provider_response": "raw-body",
            "secret": "key",
            "candidate_dump": ["x"],
        },
    )
    write_html_report([StepResult(status="failed", action="Click Login", target=target, confidence=0.9)], path=report_path)
    body = report_path.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body
    assert "hierarchy_xml" not in body
    assert "screenshot_bytes" not in body
    assert "base64" not in body
    assert "raw_payload" not in body
    assert "provider_response" not in body
    assert "candidate_dump" not in body
