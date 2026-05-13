from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import build_report_analytics, write_html_report


def test_html_report_renders_graph_query_diagnostics_section_when_present(tmp_path):
    result = StepResult(
        status="passed",
        action="Click Login",
        confidence=0.92,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.92,
            resolver_name="x",
            metadata={
                "graph_query_diagnostics": {
                    "status": "applied",
                    "relation_type": "label_for",
                    "anchor_resolution": "resolved",
                    "scope_resolution": "n/a",
                    "matched_ids": ["id-1", "id-2"],
                    "excluded_ids": ["id-x"],
                    "ambiguity": False,
                    "reasons": ["ok"],
                }
            },
        ),
    )
    out = tmp_path / "report.html"
    write_html_report([result], path=out)
    html = out.read_text(encoding="utf-8")
    assert "Graph Query Diagnostics" in html
    assert "label_for" in html
    assert "id-1" in html
    assert "id-2" in html


def test_html_report_hides_graph_query_diagnostics_section_when_absent(tmp_path):
    result = StepResult(status="passed", action="Click", confidence=1.0)
    out = tmp_path / "report.html"
    write_html_report([result], path=out)
    html = out.read_text(encoding="utf-8")
    assert "Graph Query Diagnostics" not in html


def test_html_report_escapes_graph_query_diagnostics_values_and_redacts_unsafe(tmp_path):
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
                    "status": "applied<script>alert(1)</script>",
                    "relation_type": "within_modal",
                    "matched_ids": ["<b>1</b>"],
                    "raw_payload": {"secret": "x"},
                    "nodes": [{"id": "n1"}],
                }
            },
        ),
    )
    out = tmp_path / "report.html"
    write_html_report([result], path=out)
    html = out.read_text(encoding="utf-8")
    assert "applied&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "raw_payload" not in html
    assert "nodes" not in html


def test_analytics_includes_graph_query_summary_counts():
    results = [
        StepResult(
            status="passed",
            action="A",
            confidence=0.9,
            target=ResolvedTarget(
                ref="x",
                confidence=0.9,
                resolver_name="r1",
                metadata={
                    "graph_query_diagnostics": {
                        "status": "applied",
                        "relation_type": "label_for",
                        "ambiguity": False,
                        "reasons": ["ok"],
                        "matched_ids": ["a", "b"],
                    }
                },
            ),
        ),
        StepResult(
            status="failed",
            action="B",
            confidence=0.4,
            target=ResolvedTarget(
                ref="y",
                confidence=0.4,
                resolver_name="r2",
                metadata={
                    "graph_query_diagnostics": {
                        "status": "ambiguous",
                        "relation_type": "within_modal",
                        "ambiguity": True,
                        "reasons": ["multiple_anchors", "scope_unclear"],
                        "matched_ids": ["c"],
                    }
                },
            ),
        ),
    ]

    analytics = build_report_analytics(results)
    gq = analytics["graph_query_summary"]
    assert gq["total_events"] == 2
    assert gq["status_counts"] == {"applied": 1, "ambiguous": 1}
    assert gq["relation_type_counts"] == {"label_for": 1, "within_modal": 1}
    assert gq["ambiguity_count"] == 1
    assert gq["reason_counts"] == {"ok": 1, "multiple_anchors": 1, "scope_unclear": 1}
    assert gq["matched_id_total"] == 3
