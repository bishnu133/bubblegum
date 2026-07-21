"""
tests/unit/test_summary_report.py
=================================
a54 — cross-run suite summary. Each test run upserts (keyed by suite_name) into
a manifest and renders an aggregated HTML overview with grand totals.
"""

from __future__ import annotations

import json

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.summary_report import compute_run_summary, write_summary


def _mk(*statuses):
    return [StepResult(status=s, action=f"step-{i}", duration_ms=100) for i, s in enumerate(statuses)]


def test_compute_run_summary_counts_and_status():
    rec = compute_run_summary(_mk("passed", "recovered", "skipped", "dry_run"), "T1")
    assert rec["name"] == "T1"
    assert rec["status"] == "passed"       # no failed step
    assert rec["total"] == 4
    assert rec["passed"] == 1 and rec["recovered"] == 1 and rec["skipped"] == 1 and rec["dry_run"] == 1


def test_run_status_failed_when_any_step_failed():
    rec = compute_run_summary(_mk("passed", "failed"), "T2")
    assert rec["status"] == "failed" and rec["failed"] == 1


def test_write_summary_aggregates_multiple_tests(tmp_path):
    html = tmp_path / "bubblegum-summary.html"
    write_summary(_mk("passed", "recovered"), html, suite_name="Badge Creation")
    write_summary(_mk("passed", "passed", "skipped"), html, suite_name="EDSH Challenge Creation")

    manifest = json.loads((tmp_path / "bubblegum-summary.json").read_text())
    names = {r["name"] for r in manifest["runs"]}
    assert names == {"Badge Creation", "EDSH Challenge Creation"}

    text = html.read_text()
    assert "Badge Creation" in text and "EDSH Challenge Creation" in text
    assert "Tests" in text and "Self-healed" in text


def test_combined_report_has_tabs_and_per_test_detail(tmp_path):
    html = tmp_path / "bubblegum-summary.html"
    write_summary(_mk("passed", "recovered"), html, suite_name="Badge Creation")
    write_summary(_mk("passed", "passed"), html, suite_name="EDSH Challenge Creation")
    text = html.read_text()

    # Two tabs: Summary + Test details.
    assert 'data-panel="summary"' in text and 'data-panel="details"' in text
    assert 'id="panel-summary"' in text and 'id="panel-details"' in text
    # One collapsible per test, each embedding its detail via an isolated iframe.
    assert text.count("<details class='test") == 2
    assert text.count('srcdoc="') == 2
    # Each test's full detail report was persisted to the sidecar dir.
    detail_dir = tmp_path / "bubblegum-summary.d"
    assert (detail_dir / "Badge-Creation.html").exists()
    assert (detail_dir / "EDSH-Challenge-Creation.html").exists()


def test_manifest_records_detail_file(tmp_path):
    html = tmp_path / "s.html"
    write_summary(_mk("passed"), html, suite_name="My Test")
    manifest = json.loads((tmp_path / "s.json").read_text())
    assert manifest["runs"][0]["detail_file"] == "My-Test.html"


def test_rerun_upserts_not_duplicates(tmp_path):
    html = tmp_path / "s.html"
    write_summary(_mk("passed"), html, suite_name="EDSH")
    write_summary(_mk("passed", "failed"), html, suite_name="EDSH")   # re-run, now fails

    manifest = json.loads((tmp_path / "s.json").read_text())
    assert len(manifest["runs"]) == 1
    assert manifest["runs"][0]["status"] == "failed"


def test_corrupt_manifest_starts_fresh(tmp_path):
    html = tmp_path / "s.html"
    (tmp_path / "s.json").write_text("{ not json")
    write_summary(_mk("passed"), html, suite_name="A")   # must not raise
    manifest = json.loads((tmp_path / "s.json").read_text())
    assert len(manifest["runs"]) == 1


def test_bridge_handler_wires_summary(tmp_path):
    # The report.write bridge handler should accept a `summary` path.
    import asyncio
    from bubblegum.bridge.handlers import BridgeHandlers

    class _Session:
        results = _mk("passed", "recovered")

    class _Sessions:
        def get(self, _sid):
            return _Session()

    h = BridgeHandlers.__new__(BridgeHandlers)
    h.sessions = _Sessions()
    out = asyncio.run(h.report_write({
        "session_id": "s", "suite_name": "My Test",
        "summary": str(tmp_path / "sum.html"),
    }))
    assert "summary" in out["written"]
    assert (tmp_path / "sum.json").exists()
