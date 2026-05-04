"""JSON report writer for Bubblegum StepResult outputs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import build_report_analytics


def write_json_report(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum_report.json",
    title: str = "Bubblegum Test Report",
) -> Path:
    """Write a JSON report to disk for a sequence of StepResult records."""
    out_path = Path(path)
    payload = {
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "analytics": build_report_analytics(results),
        "results": [result.model_dump(mode="json") for result in results],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path.resolve()
