"""JSON report writer for Bubblegum StepResult outputs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import (
    build_report_analytics,
    safe_graph_signals_metadata,
    safe_hydration_metadata,
    sanitize_reporting_metadata,
)


def _safe_result_dump(result: StepResult) -> dict:
    payload = result.model_dump(mode="json")
    target = payload.get("target")
    if isinstance(target, dict):
        metadata = target.get("metadata")
        if isinstance(metadata, dict):
            metadata = sanitize_reporting_metadata(metadata)
            hydration = safe_hydration_metadata(metadata)
            graph_signals = safe_graph_signals_metadata(metadata)
            for key in list(metadata.keys()):
                if key.startswith("hydration_") or key in {"match_field", "match_count"}:
                    metadata.pop(key, None)
            metadata.pop("graph_signals", None)
            metadata.update(hydration)
            if graph_signals:
                metadata["graph_signals"] = graph_signals
            target["metadata"] = metadata
    return payload


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
        "results": [_safe_result_dump(result) for result in results],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path.resolve()
