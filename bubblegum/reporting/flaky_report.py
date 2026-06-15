"""
bubblegum/reporting/flaky_report.py
===================================
Flaky-test report (X1).

Renders the accumulated flaky history (from the SQLite memory layer, via
``FlakyTracker.summary()``) into a JSON document ranking the flakiest steps —
"top N most-flaky" with their historical pass-rate — for CI dashboards and
triage. Stdlib-only, mirroring the other ``reporting/*`` writers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from bubblegum.core.flaky import FlakyRecord


def build_flaky_report(
    records: Sequence[FlakyRecord],
    *,
    stability_threshold: float,
    min_runs: int,
) -> dict:
    """Build the JSON-serializable flaky report from FlakyRecords."""
    flaky = [r for r in records if r.flaky]
    return {
        "version": 1,
        "stability_threshold": stability_threshold,
        "min_runs": min_runs,
        "total_steps": len(records),
        "flaky_count": len(flaky),
        "flaky": [_record_dict(r) for r in flaky],
        "steps": [_record_dict(r) for r in records],
    }


def _record_dict(r: FlakyRecord) -> dict:
    return {
        "step_key": r.step_key,
        "label": r.label,
        "runs": r.runs,
        "passes": r.passes,
        "fails": r.fails,
        "pass_rate": r.pass_rate,
        "flaky": r.flaky,
    }


def write_flaky_report(
    records: Sequence[FlakyRecord],
    path: str | Path = "bubblegum_flaky.json",
    *,
    stability_threshold: float = 0.90,
    min_runs: int = 3,
) -> Path:
    """Write the flaky report JSON to disk and return its path."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_flaky_report(
        records, stability_threshold=stability_threshold, min_runs=min_runs
    )
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path.resolve()
