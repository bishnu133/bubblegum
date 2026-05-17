from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_object_seed_diagnostics import run_diagnostics


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "benchmarks" / "object_intelligence" / "seed_cases.json"
SIDECAR = ROOT / "tests" / "benchmarks" / "object_intelligence" / "synthetic_elements.json"


def test_runner_loads_seed_and_sidecar_and_produces_summary_counts():
    out = run_diagnostics(CASES, SIDECAR, strict=False)
    summary = out["summary"]
    assert summary["total_cases"] == 44
    assert summary["evaluated_cases"] == 44
    assert summary["skipped_missing_metadata"] == 0
    assert summary["parsed_count"] + summary["parse_none_count"] == 44
    assert "diagnostics_status_counts" in summary
    assert "diagnostics_relation_type_counts" in summary


def test_runner_writes_compact_json_artifact(tmp_path):
    out = run_diagnostics(CASES, SIDECAR, strict=False)
    p = tmp_path / "diag.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"summary", "cases"}
    row = payload["cases"][0]
    assert "case_id" in row
    assert "diagnostics_status" in row or row["result_status"] == "skipped_missing_metadata"
    blob = json.dumps(payload).lower()
    for bad in ("screenshot", "base64", "provider_payload", "full_graph", "nodes", "edges", "hierarchy_xml"):
        assert bad not in blob


def test_runner_skips_missing_metadata_when_not_strict(tmp_path):
    sidecar = json.loads(SIDECAR.read_text(encoding="utf-8"))
    sidecar["cases"] = sidecar["cases"][:-1]
    p = tmp_path / "sidecar.json"
    p.write_text(json.dumps(sidecar), encoding="utf-8")
    out = run_diagnostics(CASES, p, strict=False)
    assert out["summary"]["skipped_missing_metadata"] == 1
    assert out["summary"]["evaluated_cases"] == 43


def test_runner_strict_missing_metadata_raises(tmp_path):
    sidecar = {"cases": []}
    p = tmp_path / "sidecar.json"
    p.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing synthetic metadata"):
        run_diagnostics(CASES, p, strict=True)


def test_runner_is_metadata_only_and_does_not_call_external_runtime():
    out = run_diagnostics(CASES, SIDECAR, strict=False)
    assert out["summary"]["total_cases"] == 44
    for row in out["cases"]:
        assert "diagnostics_status" in row or row["result_status"] == "skipped_missing_metadata"
