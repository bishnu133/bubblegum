"""JSON report writer for Bubblegum StepResult outputs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult
from bubblegum.reporting.html_report import (
    build_report_analytics,
    safe_graph_query_diagnostics_metadata,
    safe_graph_signals_metadata,
    safe_hydration_metadata,
    safe_webview_switch_diagnostics_metadata,
    safe_webview_switch_eligibility_metadata,
    safe_webview_context_selection_metadata,
    safe_webview_switch_execution_metadata,
    safe_system_dialog_detection_metadata,
    safe_system_dialog_guardrails_metadata,
    safe_system_dialog_action_metadata,
    safe_repeated_region_diagnostics_metadata,
    safe_scroll_discovery_metadata,
    safe_scroll_resolution_metadata,
    safe_icon_detection_metadata,
    safe_mobile_memory_signature_metadata,
    safe_cloud_provider_summary_metadata,
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
            graph_query_diagnostics = safe_graph_query_diagnostics_metadata(metadata)
            webview_diagnostics = safe_webview_switch_diagnostics_metadata(metadata)
            webview_switch_eligibility = safe_webview_switch_eligibility_metadata(metadata)
            webview_context_selection = safe_webview_context_selection_metadata(metadata)
            webview_switch_execution = safe_webview_switch_execution_metadata(metadata)
            system_dialog_detection = safe_system_dialog_detection_metadata(metadata)
            system_dialog_guardrails = safe_system_dialog_guardrails_metadata(metadata)
            system_dialog_action = safe_system_dialog_action_metadata(metadata)
            repeated_region_diagnostics = safe_repeated_region_diagnostics_metadata(metadata)
            scroll_discovery = safe_scroll_discovery_metadata(metadata)
            scroll_resolution = safe_scroll_resolution_metadata(metadata)
            icon_detection = safe_icon_detection_metadata(metadata)
            mobile_memory_signature = safe_mobile_memory_signature_metadata(metadata)
            cloud_provider_summary = safe_cloud_provider_summary_metadata(metadata)
            for key in list(metadata.keys()):
                if key.startswith("hydration_") or key in {"match_field", "match_count"}:
                    metadata.pop(key, None)
            metadata.pop("graph_signals", None)
            metadata.pop("graph_query_diagnostics", None)
            metadata.pop("webview_switch_diagnostics", None)
            metadata.pop("webview_switch_eligibility", None)
            metadata.pop("webview_context_selection", None)
            metadata.pop("webview_switch_execution", None)
            metadata.pop("system_dialog_detection", None)
            metadata.pop("system_dialog_guardrails", None)
            metadata.pop("system_dialog_action", None)
            metadata.pop("repeated_region_diagnostics", None)
            metadata.pop("scroll_discovery", None)
            metadata.pop("scroll_resolution", None)
            metadata.pop("icon_detection", None)
            metadata.pop("mobile_memory_signature", None)
            metadata.pop("cloud_provider_metadata", None)
            metadata.pop("cloud_provider_summary", None)
            metadata.update(hydration)
            if graph_signals:
                metadata["graph_signals"] = graph_signals
            if graph_query_diagnostics:
                metadata["graph_query_diagnostics"] = graph_query_diagnostics
            if webview_diagnostics:
                metadata["webview_switch_diagnostics"] = webview_diagnostics
            if webview_switch_eligibility:
                metadata["webview_switch_eligibility"] = webview_switch_eligibility
            if webview_context_selection:
                metadata["webview_context_selection"] = webview_context_selection
            if webview_switch_execution:
                metadata["webview_switch_execution"] = webview_switch_execution
            if system_dialog_detection:
                metadata["system_dialog_detection"] = system_dialog_detection
            if system_dialog_guardrails:
                metadata["system_dialog_guardrails"] = system_dialog_guardrails
            if system_dialog_action:
                metadata["system_dialog_action"] = system_dialog_action
            if repeated_region_diagnostics:
                metadata["repeated_region_diagnostics"] = repeated_region_diagnostics
            if scroll_discovery:
                metadata["scroll_discovery"] = scroll_discovery
            if scroll_resolution:
                metadata["scroll_resolution"] = scroll_resolution
            if icon_detection:
                metadata["icon_detection"] = icon_detection
            if mobile_memory_signature:
                metadata["mobile_memory_signature"] = mobile_memory_signature
            if cloud_provider_summary:
                metadata["cloud_provider_summary"] = cloud_provider_summary
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
