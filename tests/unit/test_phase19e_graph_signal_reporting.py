from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import build_report_analytics, write_html_report


def test_analytics_includes_graph_signal_summary_counts():
    results = [
        StepResult(
            status="passed",
            action="Click",
            confidence=0.9,
            target=ResolvedTarget(
                ref='text="Login"',
                confidence=0.9,
                resolver_name="accessibility_tree",
                metadata={
                    "graph_signals": {
                        "label_for_match": True,
                        "same_row_match": False,
                        "same_container_match": True,
                        "nearby_label_match": False,
                        "role_match_with_graph_context": True,
                        "unique_in_scope": True,
                        "visible_enabled_match": True,
                        "score_hint": 0.714,
                        "reason": "ok",
                    }
                },
            ),
        ),
        StepResult(status="failed", action="Submit", confidence=0.4),
    ]

    analytics = build_report_analytics(results)
    gs = analytics["graph_signal_summary"]
    assert gs["total_events"] == 1
    assert gs["reason_counts"] == {"ok": 1}
    assert gs["presence_counts"]["label_for_match"] == 1
    assert gs["presence_counts"]["score_hint"] == 1
    assert gs["field_true_counts"]["label_for_match"] == 1
    assert gs["field_true_counts"]["same_container_match"] == 1
    assert "same_row_match" not in gs["field_true_counts"]


def test_html_report_renders_graph_signals_section_and_redacts_unsafe_keys(tmp_path):
    report_path = tmp_path / "bubblegum_report.html"
    result = StepResult(
        status="passed",
        action="Click",
        confidence=0.9,
        target=ResolvedTarget(
            ref='text="Login"',
            confidence=0.9,
            resolver_name="accessibility_tree",
            metadata={
                "graph_signals": {
                    "label_for_match": True,
                    "score_hint": 0.286,
                    "reason": "ok",
                    "hierarchy_xml": "<root/>",
                    "raw_payload": {"secret": "x"},
                    "full_graph": {"nodes": []},
                }
            },
        ),
    )

    write_html_report([result], path=report_path)
    html = report_path.read_text(encoding="utf-8")
    assert "Graph Signals" in html
    assert "label_for_match" in html
    assert "0.286" in html
    assert "reason" in html
    assert "hierarchy_xml" not in html
    assert "raw_payload" not in html
    assert "full_graph" not in html
