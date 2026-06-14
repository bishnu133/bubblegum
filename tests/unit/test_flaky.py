"""Unit tests for flaky-test detection / quarantine (X1).

Covers the pure classification logic, the SQLite flaky-history accumulation,
the FlakyTracker run recording + summary, the flaky JSON report, and the JUnit
flaky badges + quarantine downgrade.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from bubblegum.core.config import FlakyConfig
from bubblegum.core.flaky import (
    FlakyRecord,
    FlakyTracker,
    classify,
    outcome_passed,
    step_identity,
    summarize,
)
from bubblegum.core.memory.layer import MemoryLayer
from bubblegum.core.schemas import ErrorInfo, ResolvedTarget, StepResult
from bubblegum.reporting.flaky_report import build_flaky_report, write_flaky_report
from bubblegum.reporting.junit_report import build_junit_tree


def _result(action, status, *, screen_sig=None):
    meta = {"screen_signature": screen_sig} if screen_sig else {}
    target = ResolvedTarget(ref="x", confidence=1.0, resolver_name="t", metadata=meta)
    err = ErrorInfo(error_type="E", message="boom") if status == "failed" else None
    return StepResult(status=status, action=action, target=target, confidence=1.0, error=err)


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------


def test_outcome_passed_mapping():
    assert outcome_passed("passed") is True
    assert outcome_passed("recovered") is True
    assert outcome_passed("failed") is False
    assert outcome_passed("dry_run") is None
    assert outcome_passed("skipped") is None


def test_step_identity_stable_and_screen_scoped():
    a = step_identity(_result("Click Login", "passed"))
    b = step_identity(_result("click   login", "failed"))  # case/space-insensitive
    assert a[0] == b[0]
    assert a[1] == "Click Login"
    # Different screen signature → different key.
    c = step_identity(_result("Click Login", "passed", screen_sig="scr-2"))
    assert c[0] != a[0]


@pytest.mark.parametrize(
    "runs,passes,expect_flaky",
    [
        (3, 2, True),    # 0.67 intermittent
        (3, 3, False),   # always passes → stable
        (3, 0, False),   # always fails → broken, not flaky
        (2, 1, False),   # below min_runs
        (10, 10, False),
        (10, 1, True),   # 0.10 intermittent
    ],
)
def test_classify(runs, passes, expect_flaky):
    is_flaky, _rate = classify(runs, passes, stability_threshold=0.90, min_runs=3)
    assert is_flaky is expect_flaky


def test_classify_threshold_boundary():
    # 19/20 = 0.95 ≥ 0.90 threshold → not flaky.
    assert classify(20, 19, stability_threshold=0.90, min_runs=3)[0] is False
    # raise threshold to 0.99 → now flaky.
    assert classify(20, 19, stability_threshold=0.99, min_runs=3)[0] is True


def test_summarize_orders_flaky_first_then_least_stable():
    rows = [
        {"step_key": "k1", "label": "stable", "runs": 5, "passes": 5},
        {"step_key": "k2", "label": "flaky-bad", "runs": 10, "passes": 2},
        {"step_key": "k3", "label": "flaky-ok", "runs": 10, "passes": 8},
    ]
    out = summarize(rows, stability_threshold=0.90, min_runs=3)
    assert [r.label for r in out] == ["flaky-bad", "flaky-ok", "stable"]
    assert out[0].flaky and out[1].flaky and not out[2].flaky


# ---------------------------------------------------------------------------
# MemoryLayer flaky history
# ---------------------------------------------------------------------------


def test_memory_flaky_accumulates(tmp_path):
    mem = MemoryLayer(db_path=tmp_path / "m.db", wal=False)
    mem.record_flaky_outcome("k", "Click Login", passed=True)
    mem.record_flaky_outcome("k", "Click Login", passed=False)
    mem.record_flaky_outcome("k", "Click Login", passed=True)
    rows = {r["step_key"]: r for r in mem.flaky_rows()}
    assert rows["k"]["runs"] == 3
    assert rows["k"]["passes"] == 2
    assert rows["k"]["fails"] == 1
    assert rows["k"]["last_outcome"] == "pass"


# ---------------------------------------------------------------------------
# FlakyTracker
# ---------------------------------------------------------------------------


def test_tracker_records_one_observation_per_step_per_run(tmp_path):
    mem = MemoryLayer(db_path=tmp_path / "m.db", wal=False)
    tracker = FlakyTracker(mem, stability_threshold=0.90, min_runs=3)

    # 3 runs of the same two steps; "Click Login" fails once.
    tracker.record_run([_result("Click Login", "passed"), _result("Open Menu", "passed")])
    tracker.record_run([_result("Click Login", "failed"), _result("Open Menu", "passed"),
                        _result("Preview", "dry_run")])  # dry_run ignored
    tracker.record_run([_result("Click Login", "passed"), _result("Open Menu", "passed")])

    index = tracker.flaky_index()
    summary = {r.label: r for r in tracker.summary()}
    assert summary["Click Login"].runs == 3
    assert summary["Click Login"].passes == 2
    assert summary["Click Login"].flaky is True
    assert summary["Open Menu"].flaky is False     # always passed
    # flaky_index only contains flaky steps.
    login_key = step_identity(_result("Click Login", "passed"))[0]
    assert login_key in index
    assert step_identity(_result("Open Menu", "passed"))[0] not in index


def test_tracker_run_dedup_fail_wins(tmp_path):
    mem = MemoryLayer(db_path=tmp_path / "m.db", wal=False)
    tracker = FlakyTracker(mem)
    # Same step twice in one run: a fail anywhere makes the run a fail.
    tracker.record_run([_result("Tap X", "passed"), _result("Tap X", "failed")])
    rows = {r["step_key"]: r for r in mem.flaky_rows()}
    only = next(iter(rows.values()))
    assert only["runs"] == 1 and only["fails"] == 1 and only["passes"] == 0


# ---------------------------------------------------------------------------
# Flaky report
# ---------------------------------------------------------------------------


def test_build_flaky_report_structure():
    records = [
        FlakyRecord("k2", "flaky", 10, 2, 8, 0.2, True),
        FlakyRecord("k1", "stable", 5, 5, 0, 1.0, False),
    ]
    report = build_flaky_report(records, stability_threshold=0.9, min_runs=3)
    assert report["total_steps"] == 2
    assert report["flaky_count"] == 1
    assert report["flaky"][0]["label"] == "flaky"
    assert report["flaky"][0]["pass_rate"] == 0.2


def test_write_flaky_report(tmp_path):
    import json
    records = [FlakyRecord("k", "flaky", 4, 1, 3, 0.25, True)]
    path = write_flaky_report(records, tmp_path / "f.json", stability_threshold=0.9, min_runs=3)
    data = json.loads(path.read_text())
    assert data["flaky_count"] == 1
    assert data["flaky"][0]["label"] == "flaky"


# ---------------------------------------------------------------------------
# JUnit integration: flaky badges + quarantine
# ---------------------------------------------------------------------------


def _flaky_index_for(result, *, runs=3, passes=1):
    key, label = step_identity(result)
    rec = FlakyRecord(key, label, runs, passes, runs - passes, round(passes / runs, 4), True)
    return {key: rec}


def test_junit_flaky_badge_added():
    result = _result("Click Login", "passed")
    tree = build_junit_tree([result], flaky_index=_flaky_index_for(result))
    root = tree.getroot()
    tc = root.find(".//testcase")
    props = {p.get("name"): p.get("value") for p in tc.findall("./properties/property")}
    assert props.get("flaky") == "true"
    assert "pass_rate" in props
    assert "FLAKY" in (tc.findtext("system-out") or "")


def test_junit_quarantine_downgrades_failed_flaky():
    result = _result("Click Login", "failed")
    index = _flaky_index_for(result)
    tree = build_junit_tree([result], flaky_index=index, quarantine=True)
    root = tree.getroot()
    suite = root.find("testsuite")
    # Quarantined: no failure counted, surfaced as skipped instead.
    assert suite.get("failures") == "0"
    assert suite.get("skipped") == "1"
    tc = root.find(".//testcase")
    assert tc.find("failure") is None
    assert tc.find("skipped") is not None
    assert "Quarantined" in (tc.findtext("system-out") or "")


def test_junit_failed_flaky_without_quarantine_still_fails():
    result = _result("Click Login", "failed")
    index = _flaky_index_for(result)
    tree = build_junit_tree([result], flaky_index=index, quarantine=False)
    suite = tree.getroot().find("testsuite")
    assert suite.get("failures") == "1"
    tc = tree.getroot().find(".//testcase")
    assert tc.find("failure") is not None
    # Still badged flaky.
    props = {p.get("name"): p.get("value") for p in tc.findall("./properties/property")}
    assert props.get("flaky") == "true"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_flaky_config_defaults_and_validation():
    cfg = FlakyConfig()
    assert cfg.enabled is True
    assert cfg.stability_threshold == 0.90
    assert cfg.min_runs == 3
    assert cfg.quarantine is False
    with pytest.raises(ValueError):
        FlakyConfig(stability_threshold=2.0)
    with pytest.raises(ValueError):
        FlakyConfig(min_runs=0)
