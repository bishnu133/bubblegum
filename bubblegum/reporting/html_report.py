"""
bubblegum/reporting/html_report.py
===================================
Simple single-file HTML report for Bubblegum step results.

Usage:
    from bubblegum.reporting.html_report import write_html_report
    write_html_report(results, path="report.html")

Per-step output:
  - Status badge (passed / recovered / failed / skipped)
  - Resolver that won
  - Confidence score (colour-coded)
  - Duration (ms)
  - Screenshot thumbnail (if artifact present)
  - Error message (if failed)

No external CSS dependencies — all styles are inlined.

Phase 1B — fully implemented.
"""

from __future__ import annotations

import base64
import html
from collections import Counter
from typing import Any
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult

# ---------------------------------------------------------------------------
# Colour palette (inline — no external deps)
# ---------------------------------------------------------------------------
_STATUS_COLOURS = {
    "passed":    "#22c55e",   # green-500
    "recovered": "#f59e0b",   # amber-500
    "failed":    "#ef4444",   # red-500
    "skipped":   "#94a3b8",   # slate-400
}

_CONF_HIGH   = "#22c55e"   # >= 0.85
_CONF_MEDIUM = "#f59e0b"   # >= 0.70
_CONF_LOW    = "#ef4444"   # < 0.70

_SAFE_HYDRATION_FIELDS = (
    "hydration_status",
    "hydration_reason",
    "hydration_source",
    "hydration_strategy",
    "hydration_channel",
    "hydration_original_ref",
    "hydration_hydrated_ref",
    "match_field",
    "match_count",
)

_UNSAFE_HYDRATION_KEYS = {
    "hierarchy_xml",
    "a11y_snapshot",
    "screenshot",
    "screenshot_bytes",
    "image_bytes",
    "base64",
    "raw_payload",
    "provider_body",
    "provider_request",
    "provider_response",
    "secret",
    "secrets",
    "candidate_dump",
    "candidates",
}

_UNSAFE_RETRY_KEYS = {
    "retry_stack",
    "retry_traceback",
    "retry_exception",
    "retry_payload",
    "retry_request",
    "retry_response",
    "retry_secret",
    "retry_secrets",
    "retry_candidate_dump",
}


_UNSAFE_WAIT_KEYS = {
    "wait_stack",
    "wait_traceback",
    "wait_exception",
    "wait_payload",
    "wait_request",
    "wait_response",
    "wait_secret",
    "wait_secrets",
    "wait_candidate_dump",
}

_SAFE_GRAPH_QUERY_DIAGNOSTIC_FIELDS = (
    "status",
    "relation_type",
    "anchor_resolution",
    "scope_resolution",
    "matched_ids",
    "excluded_ids",
    "ambiguity",
    "reasons",
)

_SAFE_WEBVIEW_DIAGNOSTIC_FIELDS = (
    "status",
    "recommended_context",
    "switch_required_future",
    "switch_attempted",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
)
_SAFE_WEBVIEW_SWITCH_ELIGIBILITY_FIELDS = (
    "decision", "reason", "eligible_surface", "opt_in_present", "diagnostics_candidate",
    "guardrails_allowed", "webview_context_available", "multi_webview", "system_dialog_blocking",
    "instruction_hint_type", "switch_attempted", "evidence", "warnings", "safe_metadata_only",
)
_SAFE_WEBVIEW_CONTEXT_SELECTION_FIELDS = (
    "decision", "reason", "selection_policy", "selected_context_type", "selected_context_index",
    "candidate_context_count", "eligibility_decision", "switch_attempted", "evidence", "warnings",
    "safe_metadata_only",
)
_SAFE_WEBVIEW_SWITCH_EXECUTION_FIELDS = (
    "switch_enabled", "switch_attempted", "switch_status", "restore_attempted", "restore_status",
    "original_context_type", "selected_context_type", "context_selection_reason", "reason", "evidence",
    "warnings", "safe_metadata_only",
)
_SAFE_WEBVIEW_SWITCH_WIRING_PLAN_FIELDS = (
    "enabled", "reason", "operation_type", "mode", "eligibility_decision",
    "context_selection_decision", "switch_ready", "safe_metadata_only", "warnings",
)


_SAFE_SYSTEM_DIALOG_FIELDS = (
    "dialog_detected",
    "dialog_type",
    "platform",
    "owner",
    "recommended_action",
    "confidence",
    "evidence",
    "warnings",
    "safe_metadata_only",
)

_SAFE_SYSTEM_DIALOG_GUARDRAILS_FIELDS = (
    "decision",
    "reason",
    "dialog_detected",
    "dialog_type",
    "requested_action",
    "requires_opt_in",
    "opt_in_present",
    "action_attempted",
    "recommended_action",
    "evidence",
    "warnings",
    "safe_metadata_only",
)

_SAFE_SCROLL_DISCOVERY_FIELDS = (
    "scroll_needed",
    "status",
    "reason",
    "platform",
    "target_hint_type",
    "scroll_direction",
    "max_scrolls",
    "candidate_container_count",
    "evidence",
    "warnings",
    "safe_metadata_only",
)



_SAFE_SCROLL_RESOLUTION_FIELDS = (
    "enabled",
    "attempted",
    "attempt_count",
    "max_scrolls",
    "found_after_scroll",
    "final_status",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
)

_SAFE_REPEATED_REGION_FIELDS = (
    "status",
    "region_type",
    "matched_region_count",
    "candidate_count",
    "anchor_hint_type",
    "target_action_hint",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
)

_SAFE_ICON_DETECTION_FIELDS = (
    "status",
    "icon_hint_type",
    "target_icon",
    "candidate_count",
    "matched_candidate_count",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
)

_SAFE_SYSTEM_DIALOG_ACTION_FIELDS = (
    "action_requested",
    "candidate_found",
    "action_attempted",
    "action_status",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
)



_UNSAFE_SCROLL_RESOLUTION_KEYS = {
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "screenshot",
    "screenshot_bytes",
    "page_source",
    "provider_payload",
    "raw_context_name",
    "package_name",
    "process_name",
    "exception_trace",
    "raw_instruction",
}

_UNSAFE_SCROLL_DISCOVERY_KEYS = {
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "screenshot",
    "screenshot_bytes",
    "page_source",
    "provider_payload",
    "raw_context_name",
    "package_name",
    "process_name",
    "exception_trace",
    "raw_instruction",
}
_UNSAFE_WEBVIEW_SWITCH_EXECUTION_KEYS = {
    "raw_context_name", "raw_context_names", "context_name", "context_names", "selected_context_name",
    "original_context_name", "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes",
    "page_source", "provider_payload", "raw_capabilities", "credentials", "secrets", "exception_trace",
    "exception_message",
}
_UNSAFE_WEBVIEW_SWITCH_WIRING_PLAN_KEYS = {
    "raw_context_name", "raw_context_names", "context_name", "context_names", "selected_context_name",
    "original_context_name", "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes",
    "page_source", "provider_payload", "raw_capabilities", "credentials", "secrets", "exception_trace",
    "exception_message", "raw_instruction",
}

_UNSAFE_SYSTEM_DIALOG_KEYS = {
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "screenshot",
    "screenshot_bytes",
    "page_source",
    "provider_payload",
    "raw_context_name",
    "package_name",
    "process_name",
    "exception_trace",
    "raw_instruction",
}
_UNSAFE_REPEATED_REGION_KEYS = {
    "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
    "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace", "raw_instruction",
    "raw_anchor_text", "raw_candidate_text", "selected_candidate_ref",
}

_UNSAFE_ICON_DETECTION_KEYS = {
    "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
    "provider_payload", "raw_context_name", "package_name", "process_name", "exception_trace", "raw_instruction",
    "raw_candidate_text", "raw_content_desc", "raw_resource_id",
}


_SAFE_MOBILE_MEMORY_SIGNATURE_FIELDS = (
    "enabled",
    "platform",
    "surface_type",
    "context_mode",
    "dialog_state",
    "scroll_state",
    "repeated_region_status",
    "icon_target",
    "signature_parts",
    "warnings",
    "safe_metadata_only",
)

_UNSAFE_MOBILE_MEMORY_SIGNATURE_KEYS = {
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "screenshot",
    "screenshot_bytes",
    "page_source",
    "provider_payload",
    "raw_context_name",
    "package_name",
    "process_name",
    "raw_capabilities",
    "exception_trace",
    "raw_instruction",
    "raw_candidate_text",
    "raw_content_desc",
    "raw_resource_id",
    "credentials",
    "secrets",
}

_UNSAFE_WEBVIEW_DIAGNOSTIC_KEYS = {
    "raw_xml",
    "hierarchy_xml",
    "raw_dom",
    "screenshot",
    "screenshot_bytes",
    "page_source",
    "provider_payload",
    "raw_context_name",
    "package_name",
    "process_name",
}
_UNSAFE_WEBVIEW_SWITCH_ELIGIBILITY_KEYS = {
    "raw_xml", "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source",
    "provider_payload", "raw_context_name", "raw_context_names", "context_name", "context_names",
    "package_name", "process_name", "raw_capabilities", "credentials", "secrets", "raw_instruction",
}
_UNSAFE_WEBVIEW_CONTEXT_SELECTION_KEYS = {
    "raw_context_name", "raw_context_names", "context_name", "context_names", "raw_xml",
    "hierarchy_xml", "raw_dom", "screenshot", "screenshot_bytes", "page_source", "provider_payload",
    "raw_capabilities", "credentials", "secrets",
}


_SAFE_CLOUD_PROVIDER_SUMMARY_FIELDS = (
    "provider",
    "provider_namespace",
    "platform",
    "device_name_present",
    "app_launch_strategy",
    "url_source",
    "automation_name",
    "session_name_present",
    "build_name_present",
    "safe_metadata_only",
    "warnings",
)

_UNSAFE_CLOUD_PROVIDER_KEYS = {
    "username", "access_key", "password", "token", "secret", "credentials",
    "raw_capabilities", "provider_payload", "raw_url", "app", "app_id",
    "package_name", "process_name", "raw_context_name", "raw_xml", "hierarchy_xml",
    "raw_dom", "screenshot", "screenshot_bytes", "page_source",
}

_SAFE_GRAPH_SIGNAL_FIELDS = (
    "label_for_match",
    "same_row_match",
    "same_container_match",
    "nearby_label_match",
    "role_match_with_graph_context",
    "unique_in_scope",
    "visible_enabled_match",
    "score_hint",
    "reason",
)

_UNSAFE_GRAPH_QUERY_DIAGNOSTIC_KEYS = {
    "raw_snapshot",
    "snapshot",
    "hierarchy_xml",
    "xml",
    "screenshot",
    "screenshot_bytes",
    "image_base64",
    "provider_payload",
    "raw_payload",
    "full_graph",
    "nodes",
    "edges",
    "raw_attributes",
}

_UNSAFE_GRAPH_KEYS = {
    "snapshot",
    "a11y_snapshot",
    "hierarchy_xml",
    "raw_xml",
    "screenshot",
    "screenshot_bytes",
    "image_bytes",
    "base64",
    "raw_payload",
    "provider_payload",
    "provider_request",
    "provider_response",
    "graph_dump",
    "full_graph",
    "nodes",
    "edges",
}


def _conf_colour(conf: float) -> str:
    if conf >= 0.85:
        return _CONF_HIGH
    if conf >= 0.70:
        return _CONF_MEDIUM
    return _CONF_LOW


def _badge(text: str, colour: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'background:{colour};color:#fff;font-weight:600;font-size:0.78rem;">'
        f'{html.escape(text)}</span>'
    )


def safe_hydration_metadata(metadata: dict) -> dict[str, str]:
    """Return report-safe hydration metadata for JSON/HTML surfaces."""
    if not isinstance(metadata, dict):
        return {}
    if any(key in metadata for key in _UNSAFE_HYDRATION_KEYS):
        metadata = {k: v for k, v in metadata.items() if k not in _UNSAFE_HYDRATION_KEYS}

    out: dict[str, str] = {}
    for key in _SAFE_HYDRATION_FIELDS:
        value = metadata.get(key)
        if value is None:
            continue
        out[key] = str(value)
    return out


def sanitize_reporting_metadata(metadata: dict) -> dict:
    """Remove known unsafe fields from report surfaces."""
    if not isinstance(metadata, dict):
        return {}
    return {k: v for k, v in metadata.items() if k not in _UNSAFE_HYDRATION_KEYS and k not in _UNSAFE_RETRY_KEYS and k not in _UNSAFE_WAIT_KEYS and k not in _UNSAFE_CLOUD_PROVIDER_KEYS}



def safe_cloud_provider_summary_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe cloud provider summary metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("cloud_provider_summary")
    if not isinstance(raw, dict):
        raw = metadata.get("cloud_provider_metadata")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_CLOUD_PROVIDER_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_CLOUD_PROVIDER_SUMMARY_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key == "warnings":
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif key in {"device_name_present", "session_name_present", "build_name_present", "safe_metadata_only"}:
            out[key] = bool(value)
        elif value is not None:
            out[key] = str(value)
    return out

def safe_graph_signals_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact report-safe graph signal metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("graph_signals")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_GRAPH_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_GRAPH_SIGNAL_FIELDS:
        if key in redacted:
            out[key] = redacted[key]
    return out


def safe_graph_query_diagnostics_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact report-safe graph query diagnostics metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("graph_query_diagnostics")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_GRAPH_QUERY_DIAGNOSTIC_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_GRAPH_QUERY_DIAGNOSTIC_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"matched_ids", "excluded_ids", "reasons"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif key == "ambiguity":
            out[key] = bool(value)
        elif value is not None:
            out[key] = str(value) if isinstance(value, (bytes, bytearray)) else value
    return out






def safe_mobile_memory_signature_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe mobile memory signature metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("mobile_memory_signature")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_MOBILE_MEMORY_SIGNATURE_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_MOBILE_MEMORY_SIGNATURE_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"enabled", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"signature_parts", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_webview_switch_diagnostics_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe webview dry-run diagnostics."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("webview_switch_diagnostics")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_WEBVIEW_DIAGNOSTIC_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_WEBVIEW_DIAGNOSTIC_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"switch_required_future", "switch_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_webview_switch_eligibility_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("webview_switch_eligibility")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_WEBVIEW_SWITCH_ELIGIBILITY_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_WEBVIEW_SWITCH_ELIGIBILITY_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"opt_in_present", "diagnostics_candidate", "guardrails_allowed", "webview_context_available", "multi_webview", "system_dialog_blocking", "switch_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_webview_context_selection_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("webview_context_selection")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_WEBVIEW_CONTEXT_SELECTION_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_WEBVIEW_CONTEXT_SELECTION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"selected_context_index", "candidate_context_count"}:
            try:
                out[key] = int(value)
            except Exception:
                continue
        elif key in {"switch_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_webview_switch_execution_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("webview_switch_execution")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_WEBVIEW_SWITCH_EXECUTION_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_WEBVIEW_SWITCH_EXECUTION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"switch_enabled", "switch_attempted", "restore_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_webview_switch_wiring_plan_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("webview_switch_wiring_plan")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_WEBVIEW_SWITCH_WIRING_PLAN_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_WEBVIEW_SWITCH_WIRING_PLAN_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"enabled", "switch_ready", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key == "warnings":
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out


def safe_repeated_region_diagnostics_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("repeated_region_diagnostics")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_REPEATED_REGION_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_REPEATED_REGION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"matched_region_count", "candidate_count"}:
            try:
                out[key] = int(value)
            except Exception:
                continue
        elif key in {"safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out



def safe_icon_detection_metadata(metadata: dict) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("icon_detection")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_ICON_DETECTION_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_ICON_DETECTION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"candidate_count", "matched_candidate_count"}:
            try:
                out[key] = int(value)
            except Exception:
                continue
        elif key in {"safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            out[key] = [str(v) for v in value] if isinstance(value, (list, tuple)) else [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_system_dialog_detection_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe system dialog detection metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("system_dialog_detection")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_SYSTEM_DIALOG_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_SYSTEM_DIALOG_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"dialog_detected", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif key == "confidence":
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                continue
        elif value is not None:
            out[key] = str(value)
    return out


def safe_system_dialog_guardrails_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe system dialog guardrail metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("system_dialog_guardrails")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_SYSTEM_DIALOG_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_SYSTEM_DIALOG_GUARDRAILS_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"dialog_detected", "requires_opt_in", "opt_in_present", "action_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out




def safe_scroll_discovery_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe mobile scroll discovery metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("scroll_discovery")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_SCROLL_DISCOVERY_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_SCROLL_DISCOVERY_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"scroll_needed", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"max_scrolls", "candidate_container_count"}:
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out




def safe_scroll_resolution_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe mobile scroll resolution metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("scroll_resolution")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_SCROLL_RESOLUTION_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_SCROLL_RESOLUTION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"enabled", "attempted", "found_after_scroll", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"attempt_count", "max_scrolls"}:
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out

def safe_system_dialog_action_metadata(metadata: dict) -> dict[str, Any]:
    """Return compact safe system dialog action metadata."""
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("system_dialog_action")
    if not isinstance(raw, dict):
        return {}
    redacted = {k: v for k, v in raw.items() if k not in _UNSAFE_SYSTEM_DIALOG_KEYS}
    out: dict[str, Any] = {}
    for key in _SAFE_SYSTEM_DIALOG_ACTION_FIELDS:
        if key not in redacted:
            continue
        value = redacted[key]
        if key in {"candidate_found", "action_attempted", "safe_metadata_only"}:
            out[key] = bool(value)
        elif key in {"evidence", "warnings"}:
            if isinstance(value, (list, tuple)):
                out[key] = [str(v) for v in value]
            elif value is not None:
                out[key] = [str(value)]
        elif value is not None:
            out[key] = str(value)
    return out


def _screenshot_thumb(path: str) -> str:
    """Return an <img> tag with an inline base64 thumbnail, or empty string on failure."""
    try:
        data = Path(path).read_bytes()
        b64  = base64.b64encode(data).decode()
        return (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="max-width:220px;max-height:140px;border-radius:4px;'
            f'border:1px solid #e2e8f0;margin-top:6px;" '
            f'alt="screenshot" />'
        )
    except Exception:
        return f'<span style="color:#94a3b8;font-size:0.8rem;">[screenshot not found: {html.escape(path)}]</span>'


def _render_step(idx: int, result: StepResult) -> str:
    status_colour = _STATUS_COLOURS.get(result.status, "#94a3b8")
    status_badge  = _badge(result.status.upper(), status_colour)
    conf_colour   = _conf_colour(result.confidence)

    resolver_name = (
        result.target.resolver_name if result.target else "—"
    )

    screenshot_html = ""
    for artifact in result.artifacts:
        if artifact.type == "screenshot":
            screenshot_html = _screenshot_thumb(artifact.path)
            break

    error_html = ""
    if result.error:
        error_html = (
            f'<div style="margin-top:8px;padding:8px;background:#fef2f2;'
            f'border-left:3px solid #ef4444;border-radius:4px;'
            f'font-size:0.82rem;color:#991b1b;">'
            f'<strong>Error:</strong> {html.escape(result.error.message)}'
            f'</div>'
        )

    traces_html = ""
    if result.traces:
        trace_rows = "".join(
            f'<tr style="border-bottom:1px solid #f1f5f9;">'
            f'<td style="padding:3px 8px;color:#475569;">{html.escape(t.resolver_name)}</td>'
            f'<td style="padding:3px 8px;color:#64748b;">{"✓" if t.can_run else "✗ skipped"}</td>'
            f'<td style="padding:3px 8px;color:#64748b;">{len(t.candidates)}</td>'
            f'<td style="padding:3px 8px;color:#64748b;">{t.duration_ms} ms</td>'
            f'</tr>'
            for t in result.traces
        )

    hydration_html = ""
    target_metadata = sanitize_reporting_metadata(result.target.metadata if result.target else {})
    hydration = safe_hydration_metadata(target_metadata)
    if hydration:
        labels = [
            ("Status", "hydration_status"),
            ("Reason", "hydration_reason"),
            ("Source", "hydration_source"),
            ("Strategy", "hydration_strategy"),
            ("Channel", "hydration_channel"),
            ("Original ref", "hydration_original_ref"),
            ("Hydrated ref", "hydration_hydrated_ref"),
            ("Match field", "match_field"),
            ("Match count", "match_count"),
        ]
        hydration_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(hydration[key])}</li>'
            for label, key in labels
            if key in hydration
        )
        hydration_html = (
            f'<details style="margin-top:8px;">'
            f'<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Hydration diagnostics</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{hydration_rows}</ul>'
            f'</details>'
        )
    graph_html = ""
    graph_signals = safe_graph_signals_metadata(target_metadata)
    if graph_signals:
        graph_rows = "".join(
            f'<li><strong>{html.escape(key)}:</strong> {html.escape(str(graph_signals[key]))}</li>'
            for key in _SAFE_GRAPH_SIGNAL_FIELDS
            if key in graph_signals
        )
        graph_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Graph Signals</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{graph_rows}</ul>'
            '</details>'
        )
    graph_query_html = ""
    graph_query_diagnostics = safe_graph_query_diagnostics_metadata(target_metadata)
    if graph_query_diagnostics:
        graph_query_rows = "".join(
            f'<li><strong>{html.escape(key)}:</strong> {html.escape(str(graph_query_diagnostics[key]))}</li>'
            for key in _SAFE_GRAPH_QUERY_DIAGNOSTIC_FIELDS
            if key in graph_query_diagnostics
        )
        graph_query_html = (
            "<details style=\"margin-top:8px;\">"
            "<summary style=\"cursor:pointer;font-size:0.8rem;color:#64748b;\">Graph Query Diagnostics</summary>"
            f'<ul style=\"margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;\">{graph_query_rows}</ul>'
            "</details>"
        )

    webview_html = ""
    webview_diagnostics = safe_webview_switch_diagnostics_metadata(target_metadata)
    webview_switch_eligibility = safe_webview_switch_eligibility_metadata(target_metadata)
    webview_context_selection = safe_webview_context_selection_metadata(target_metadata)
    webview_switch_execution = safe_webview_switch_execution_metadata(target_metadata)
    webview_switch_wiring_plan = safe_webview_switch_wiring_plan_metadata(target_metadata)
    if webview_diagnostics:
        evidence = webview_diagnostics.get("evidence", [])
        warnings = webview_diagnostics.get("warnings", [])
        evidence_display = f"{len(evidence)}" if evidence else "0"
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Status", "status"),
            ("Recommended context", "recommended_context"),
            ("Switch required future", "switch_required_future"),
            ("Switch attempted", "switch_attempted"),
            ("Reason", "reason"),
        ]
        webview_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(webview_diagnostics[key]))}</li>'
            for label, key in labels
            if key in webview_diagnostics
        )
        webview_rows += f'<li><strong>Evidence count:</strong> {html.escape(evidence_display)}</li>'
        webview_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        webview_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">WebView Dry-Run Diagnostics</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{webview_rows}</ul>'
            '</details>'
        )



    webview_switch_eligibility_html = ""
    if webview_switch_eligibility:
        evidence = webview_switch_eligibility.get("evidence", [])
        warnings = webview_switch_eligibility.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [("Decision", "decision"), ("Reason", "reason"), ("Eligible surface", "eligible_surface"), ("Opt-in present", "opt_in_present"), ("Diagnostics candidate", "diagnostics_candidate"), ("Guardrails allowed", "guardrails_allowed"), ("WebView context available", "webview_context_available"), ("Multi WebView", "multi_webview"), ("System dialog blocking", "system_dialog_blocking"), ("Instruction hint type", "instruction_hint_type"), ("Switch attempted", "switch_attempted")]
        rows = "".join(f'<li><strong>{label}:</strong> {html.escape(str(webview_switch_eligibility[key]))}</li>' for label, key in labels if key in webview_switch_eligibility)
        rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        webview_switch_eligibility_html = ('<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">WebView Switch Eligibility</summary>' f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{rows}</ul></details>')

    webview_context_selection_html = ""
    if webview_context_selection:
        evidence = webview_context_selection.get("evidence", [])
        warnings = webview_context_selection.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [("Decision", "decision"), ("Reason", "reason"), ("Selection policy", "selection_policy"), ("Selected context type", "selected_context_type"), ("Selected context index", "selected_context_index"), ("Candidate context count", "candidate_context_count"), ("Eligibility decision", "eligibility_decision"), ("Switch attempted", "switch_attempted")]
        rows = "".join(f'<li><strong>{label}:</strong> {html.escape(str(webview_context_selection[key]))}</li>' for label, key in labels if key in webview_context_selection)
        rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        webview_context_selection_html = ('<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">WebView Context Selection</summary>' f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{rows}</ul></details>')
    webview_switch_execution_html = ""
    if webview_switch_execution:
        evidence = webview_switch_execution.get("evidence", [])
        warnings = webview_switch_execution.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [("Switch enabled", "switch_enabled"), ("Switch attempted", "switch_attempted"), ("Switch status", "switch_status"), ("Restore attempted", "restore_attempted"), ("Restore status", "restore_status"), ("Original context type", "original_context_type"), ("Selected context type", "selected_context_type"), ("Context selection reason", "context_selection_reason"), ("Reason", "reason")]
        rows = "".join(f'<li><strong>{label}:</strong> {html.escape(str(webview_switch_execution[key]))}</li>' for label, key in labels if key in webview_switch_execution)
        rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        webview_switch_execution_html = ('<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">WebView Switch Execution</summary>' f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{rows}</ul></details>')

    webview_switch_wiring_plan_html = ""
    if webview_switch_wiring_plan:
        warnings = webview_switch_wiring_plan.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [("Enabled", "enabled"), ("Reason", "reason"), ("Operation type", "operation_type"), ("Mode", "mode"), ("Eligibility decision", "eligibility_decision"), ("Context selection decision", "context_selection_decision"), ("Switch ready", "switch_ready")]
        rows = "".join(f'<li><strong>{label}:</strong> {html.escape(str(webview_switch_wiring_plan[key]))}</li>' for label, key in labels if key in webview_switch_wiring_plan)
        rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        webview_switch_wiring_plan_html = ('<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">WebView Switch Wiring Plan</summary>' f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{rows}</ul></details>')

    system_dialog_html = ""
    system_dialog_detection = safe_system_dialog_detection_metadata(target_metadata)
    if system_dialog_detection:
        evidence = system_dialog_detection.get("evidence", [])
        warnings = system_dialog_detection.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Detected", "dialog_detected"),
            ("Dialog type", "dialog_type"),
            ("Platform", "platform"),
            ("Owner", "owner"),
            ("Recommended action", "recommended_action"),
            ("Confidence", "confidence"),
        ]
        system_dialog_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(system_dialog_detection[key]))}</li>'
            for label, key in labels
            if key in system_dialog_detection
        )
        system_dialog_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        system_dialog_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        system_dialog_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">System Dialog Detection</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{system_dialog_rows}</ul>'
            '</details>'
        )
    system_dialog_guardrails_html = ""
    system_dialog_guardrails = safe_system_dialog_guardrails_metadata(target_metadata)
    if system_dialog_guardrails:
        evidence = system_dialog_guardrails.get("evidence", [])
        warnings = system_dialog_guardrails.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Decision", "decision"),
            ("Reason", "reason"),
            ("Dialog detected", "dialog_detected"),
            ("Dialog type", "dialog_type"),
            ("Requested action", "requested_action"),
            ("Requires opt-in", "requires_opt_in"),
            ("Opt-in present", "opt_in_present"),
            ("Action attempted", "action_attempted"),
            ("Recommended action", "recommended_action"),
        ]
        guardrail_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(system_dialog_guardrails[key]))}</li>'
            for label, key in labels
            if key in system_dialog_guardrails
        )
        guardrail_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        guardrail_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        system_dialog_guardrails_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">System Dialog Guardrails</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{guardrail_rows}</ul>'
            '</details>'
        )
    system_dialog_action_html = ""
    system_dialog_action = safe_system_dialog_action_metadata(target_metadata)
    if system_dialog_action:
        evidence = system_dialog_action.get("evidence", [])
        warnings = system_dialog_action.get("warnings", [])
        evidence_display = ", ".join(str(e) for e in evidence) if evidence else "none"
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Action requested", "action_requested"),
            ("Candidate found", "candidate_found"),
            ("Action attempted", "action_attempted"),
            ("Status", "action_status"),
            ("Reason", "reason"),
            ("Safe metadata only", "safe_metadata_only"),
        ]
        action_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(system_dialog_action[key]))}</li>'
            for label, key in labels
            if key in system_dialog_action
        )
        action_rows += f'<li><strong>Evidence:</strong> {html.escape(evidence_display)}</li>'
        action_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        system_dialog_action_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">System Dialog Action</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{action_rows}</ul>'
            "</details>"
        )
    scroll_discovery_html = ""
    scroll_resolution_html = ""
    scroll_discovery = safe_scroll_discovery_metadata(target_metadata)
    if scroll_discovery:
        evidence = scroll_discovery.get("evidence", [])
        warnings = scroll_discovery.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Scroll needed", "scroll_needed"),
            ("Status", "status"),
            ("Reason", "reason"),
            ("Platform", "platform"),
            ("Target hint type", "target_hint_type"),
            ("Scroll direction", "scroll_direction"),
            ("Max scrolls", "max_scrolls"),
            ("Candidate container count", "candidate_container_count"),
        ]
        scroll_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(scroll_discovery[key]))}</li>'
            for label, key in labels
            if key in scroll_discovery
        )
        scroll_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        scroll_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        scroll_discovery_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Scroll Discovery</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{scroll_rows}</ul>'
            "</details>"
        )

    scroll_resolution = safe_scroll_resolution_metadata(target_metadata)
    if scroll_resolution:
        evidence = scroll_resolution.get("evidence", [])
        warnings = scroll_resolution.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        resolution_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(scroll_resolution[key]))}</li>'
            for label, key in [
                ("Enabled", "enabled"),
                ("Attempted", "attempted"),
                ("Attempt count", "attempt_count"),
                ("Max scrolls", "max_scrolls"),
                ("Found after scroll", "found_after_scroll"),
                ("Final status", "final_status"),
                ("Reason", "reason"),
                ("Safe metadata only", "safe_metadata_only"),
            ]
            if key in scroll_resolution
        )
        resolution_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        resolution_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        scroll_resolution_html = (
            '<details style="margin-top:6px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Scroll Resolution</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{resolution_rows}</ul>'
            '</details>'
        )

    repeated_region_html = ""
    repeated_region = safe_repeated_region_diagnostics_metadata(target_metadata)
    if repeated_region:
        evidence = repeated_region.get("evidence", [])
        warnings = repeated_region.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Status", "status"),
            ("Region type", "region_type"),
            ("Matched region count", "matched_region_count"),
            ("Candidate count", "candidate_count"),
            ("Anchor hint type", "anchor_hint_type"),
            ("Target action hint", "target_action_hint"),
            ("Reason", "reason"),
        ]
        repeated_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(repeated_region[key]))}</li>'
            for label, key in labels
            if key in repeated_region
        )
        repeated_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        repeated_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        repeated_region_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Repeated Region Diagnostics</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{repeated_rows}</ul>'
            '</details>'
        )
    mobile_memory_signature_html = ""
    mobile_memory_signature = safe_mobile_memory_signature_metadata(target_metadata)
    if mobile_memory_signature:
        signature_parts = mobile_memory_signature.get("signature_parts", [])
        warnings = mobile_memory_signature.get("warnings", [])
        signature_parts_display = ", ".join(str(p) for p in signature_parts) if signature_parts else "none"
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Platform", "platform"),
            ("Surface type", "surface_type"),
            ("Context mode", "context_mode"),
            ("Dialog state", "dialog_state"),
            ("Scroll state", "scroll_state"),
            ("Repeated region status", "repeated_region_status"),
            ("Icon target", "icon_target"),
        ]
        mobile_sig_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(mobile_memory_signature[key]))}</li>'
            for label, key in labels
            if key in mobile_memory_signature
        )
        mobile_sig_rows += f'<li><strong>Signature parts count:</strong> {html.escape(str(len(signature_parts)))}</li>'
        mobile_sig_rows += f'<li><strong>Signature parts:</strong> {html.escape(signature_parts_display)}</li>'
        mobile_sig_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        mobile_memory_signature_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Mobile Memory Signature</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{mobile_sig_rows}</ul>'
            '</details>'
        )

    icon_detection_html = ""
    icon_detection = safe_icon_detection_metadata(target_metadata)
    if icon_detection:
        evidence = icon_detection.get("evidence", [])
        warnings = icon_detection.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Status", "status"),
            ("Icon hint type", "icon_hint_type"),
            ("Target icon", "target_icon"),
            ("Candidate count", "candidate_count"),
            ("Matched candidate count", "matched_candidate_count"),
            ("Reason", "reason"),
        ]
        icon_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(icon_detection[key]))}</li>'
            for label, key in labels
            if key in icon_detection
        )
        icon_rows += f'<li><strong>Evidence count:</strong> {html.escape(str(len(evidence)))}</li>'
        icon_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        icon_detection_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Icon Detection</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{icon_rows}</ul>'
            '</details>'
        )
    cloud_provider_summary_html = ""
    cloud_provider_summary = safe_cloud_provider_summary_metadata(target_metadata)
    if cloud_provider_summary:
        warnings = cloud_provider_summary.get("warnings", [])
        warnings_display = ", ".join(str(w) for w in warnings) if warnings else "none"
        labels = [
            ("Provider", "provider"),
            ("Provider namespace", "provider_namespace"),
            ("Platform", "platform"),
            ("Device name present", "device_name_present"),
            ("App launch strategy", "app_launch_strategy"),
            ("URL source", "url_source"),
            ("Automation name", "automation_name"),
            ("Session name present", "session_name_present"),
            ("Build name present", "build_name_present"),
        ]
        cloud_rows = "".join(
            f'<li><strong>{label}:</strong> {html.escape(str(cloud_provider_summary[key]))}</li>'
            for label, key in labels
            if key in cloud_provider_summary
        )
        cloud_rows += f'<li><strong>Warnings:</strong> {html.escape(warnings_display)}</li>'
        cloud_provider_summary_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Cloud Provider Summary</summary>'
            f'<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">{cloud_rows}</ul>'
            '</details>'
        )

    wait_html = ""
    if target_metadata.get("wait_used") is True:
        wait_mode = target_metadata.get("wait_mode", "unknown")
        wait_outcome = target_metadata.get("wait_outcome", "unknown")
        wait_adapter = target_metadata.get("wait_adapter", "unknown")
        wait_duration_ms = target_metadata.get("wait_duration_ms")
        wait_duration_row = ""
        if wait_duration_ms is not None:
            wait_duration_row = f'<li><strong>Duration:</strong> {html.escape(str(wait_duration_ms))} ms</li>'
        wait_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Wait</summary>'
            '<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">'
            f'<li><strong>Used:</strong> true</li>'
            f'<li><strong>Mode:</strong> {html.escape(str(wait_mode))}</li>'
            f'<li><strong>Outcome:</strong> {html.escape(str(wait_outcome))}</li>'
            f'<li><strong>Adapter:</strong> {html.escape(str(wait_adapter))}</li>'
            f'{wait_duration_row}'
            '</ul></details>'
        )

    retry_html = ""
    retry_attempts = target_metadata.get("retry_attempts")
    if retry_attempts is not None:
        retry_transient = target_metadata.get("retry_transient")
        retry_reason = target_metadata.get("retry_reason", "none")
        retry_adapter = target_metadata.get("retry_adapter", "unknown")
        retry_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Retry</summary>'
            '<ul style="margin:6px 0 0 18px;color:#334155;font-size:0.82rem;line-height:1.45;">'
            f'<li><strong>Attempts:</strong> {html.escape(str(retry_attempts))}</li>'
            f'<li><strong>Transient:</strong> {html.escape(str(retry_transient))}</li>'
            f'<li><strong>Reason:</strong> {html.escape(str(retry_reason))}</li>'
            f'<li><strong>Adapter:</strong> {html.escape(str(retry_adapter))}</li>'
            '</ul></details>'
        )
    if result.traces:
        traces_html = (
            f'<details style="margin-top:8px;">'
            f'<summary style="cursor:pointer;font-size:0.8rem;color:#64748b;">Resolver traces ({len(result.traces)})</summary>'
            f'<table style="width:100%;border-collapse:collapse;margin-top:4px;font-size:0.8rem;">'
            f'<thead><tr style="background:#f8fafc;">'
            f'<th style="padding:3px 8px;text-align:left;color:#475569;">Resolver</th>'
            f'<th style="padding:3px 8px;text-align:left;color:#475569;">Status</th>'
            f'<th style="padding:3px 8px;text-align:left;color:#475569;">Candidates</th>'
            f'<th style="padding:3px 8px;text-align:left;color:#475569;">Duration</th>'
            f'</tr></thead>'
            f'<tbody>{trace_rows}</tbody>'
            f'</table>'
            f'</details>'
        )

    return f"""
    <div style="border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:12px;background:#fff;">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-weight:600;color:#1e293b;min-width:24px;">#{idx}</span>
        {status_badge}
        <span style="flex:1;font-family:monospace;font-size:0.9rem;color:#334155;">{html.escape(result.action)}</span>
        <span style="font-size:0.82rem;color:#64748b;">{result.duration_ms} ms</span>
      </div>
      <div style="margin-top:8px;display:flex;gap:20px;flex-wrap:wrap;font-size:0.84rem;color:#475569;">
        <span><strong>Resolver:</strong> {html.escape(resolver_name)}</span>
        <span><strong>Confidence:</strong>
          <span style="color:{conf_colour};font-weight:600;">{result.confidence:.2f}</span>
        </span>
      </div>
      {error_html}
      {screenshot_html}
      {hydration_html}
      {graph_html}
      {graph_query_html}
      {webview_html}
      {webview_switch_eligibility_html}
      {webview_context_selection_html}
      {webview_switch_execution_html}
      {webview_switch_wiring_plan_html}
      {system_dialog_html}
      {system_dialog_guardrails_html}
      {system_dialog_action_html}
      {scroll_discovery_html}
      {scroll_resolution_html}
      {repeated_region_html}
      {mobile_memory_signature_html}
      {icon_detection_html}
      {cloud_provider_summary_html}
      {wait_html}
      {retry_html}
      {traces_html}
    </div>
    """


def write_html_report(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum_report.html",
    title: str = "Bubblegum Test Report",
) -> Path:
    """
    Write a single-file HTML report to disk.

    Args:
        results: Ordered list of StepResult objects from a test run.
        path:    Output file path (default: bubblegum_report.html in cwd).
        title:   Report title shown in the page header.

    Returns:
        Resolved Path to the written file.
    """
    out_path = Path(path)

    analytics = build_report_analytics(results)
    status_counts = analytics["status_counts"]
    conf_summary = analytics["confidence_summary"]
    resolver_win_counts = analytics["resolver_win_counts"]
    error_type_counts = analytics["error_type_counts"]

    total = analytics["total"]
    passed = status_counts["passed"]
    recovered = status_counts["recovered"]
    failed = status_counts["failed"]
    skipped = status_counts["skipped"]

    summary_html = (
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px;">'
        f'{_summary_card("Total",     total,     "#64748b")}'
        f'{_summary_card("Passed",    passed,    _STATUS_COLOURS["passed"])}'
        f'{_summary_card("Recovered", recovered, _STATUS_COLOURS["recovered"])}'
        f'{_summary_card("Failed",    failed,    _STATUS_COLOURS["failed"])}'
        f'{_summary_card("Skipped",   skipped,   _STATUS_COLOURS["skipped"])}'
        f'</div>'
    )

    resolver_dist_html = (
        "".join(
            f"<li><strong>{html.escape(name)}</strong>: {count}</li>"
            for name, count in sorted(
                resolver_win_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        if resolver_win_counts else
        '<li style="color:#94a3b8;">No resolver wins recorded.</li>'
    )

    if conf_summary["count"]:
        confidence_summary_html = (
            f'<li>Count: <strong>{conf_summary["count"]}</strong></li>'
            f'<li>Min: <strong>{conf_summary["min"]:.2f}</strong></li>'
            f'<li>Max: <strong>{conf_summary["max"]:.2f}</strong></li>'
            f'<li>Average: <strong>{conf_summary["average"]:.2f}</strong></li>'
            f'<li>Buckets — High: <strong>{conf_summary["buckets"]["high"]}</strong>, '
            f'Medium: <strong>{conf_summary["buckets"]["medium"]}</strong>, '
            f'Low: <strong>{conf_summary["buckets"]["low"]}</strong></li>'
        )
    else:
        confidence_summary_html = '<li style="color:#94a3b8;">No confidence data.</li>'

    error_dist_html = (
        "".join(
            f"<li><strong>{html.escape(error_type)}</strong>: {count}</li>"
            for error_type, count in sorted(
                error_type_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )
        if error_type_counts else
        '<li style="color:#94a3b8;">No errors recorded.</li>'
    )

    analytics_html = f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:20px;">
      <section style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;background:#fff;">
        <h2 style="font-size:0.95rem;color:#0f172a;margin-bottom:8px;">Resolver Win Distribution</h2>
        <ul style="margin-left:18px;color:#334155;font-size:0.84rem;line-height:1.45;">{resolver_dist_html}</ul>
      </section>
      <section style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;background:#fff;">
        <h2 style="font-size:0.95rem;color:#0f172a;margin-bottom:8px;">Confidence Summary</h2>
        <ul style="margin-left:18px;color:#334155;font-size:0.84rem;line-height:1.45;">{confidence_summary_html}</ul>
      </section>
      <section style="border:1px solid #e2e8f0;border-radius:8px;padding:12px;background:#fff;">
        <h2 style="font-size:0.95rem;color:#0f172a;margin-bottom:8px;">Error Type Distribution</h2>
        <ul style="margin-left:18px;color:#334155;font-size:0.84rem;line-height:1.45;">{error_dist_html}</ul>
      </section>
    </div>
    """

    steps_html = "".join(_render_step(i + 1, r) for i, r in enumerate(results))

    if not results:
        steps_html = '<p style="color:#94a3b8;">No steps recorded.</p>'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc;
      color: #1e293b;
      padding: 32px 24px;
    }}
    h1 {{ font-size: 1.5rem; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
    .subtitle {{ font-size: 0.85rem; color: #64748b; margin-bottom: 24px; }}
    details summary::-webkit-details-marker {{ display: none; }}
  </style>
</head>
<body>
  <h1>🧠 {html.escape(title)}</h1>
  <div class="subtitle">Generated by Bubblegum — AI-powered test recovery &amp; NL execution</div>
  {summary_html}
  {analytics_html}
  {steps_html}
</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    return out_path.resolve()


def _summary_card(label: str, count: int, colour: str) -> str:
    return (
        f'<div style="padding:12px 20px;background:#fff;border-radius:8px;'
        f'border:1px solid #e2e8f0;min-width:100px;text-align:center;">'
        f'<div style="font-size:1.6rem;font-weight:700;color:{colour};">{count}</div>'
        f'<div style="font-size:0.78rem;color:#64748b;margin-top:2px;">{html.escape(label)}</div>'
        f'</div>'
    )


def _count_categorical_field(counter: Counter[str], value: Any) -> None:
    if isinstance(value, str) and value:
        counter[value] += 1


def build_report_analytics(results: Sequence[StepResult]) -> dict:
    """
    Build aggregate analytics for a list of StepResult objects.

    Returned structure:
      - total
      - status_counts
      - resolver_win_counts
      - confidence_summary {count,min,max,average,buckets}
      - error_type_counts
      - hydration_summary {total_events,status_counts,by_source,by_strategy,by_channel,by_reason}
      - graph_signal_summary {total_events,presence_counts,reason_counts,field_true_counts}
      - graph_query_summary {total_events,status_counts,relation_type_counts,ambiguity_count,reason_counts,matched_id_total}
    """
    status_counts = Counter(
        {"passed": 0, "recovered": 0, "failed": 0, "skipped": 0}
    )
    resolver_win_counts: Counter[str] = Counter()
    error_type_counts: Counter[str] = Counter()

    confidences: list[float] = []
    confidence_buckets = {"high": 0, "medium": 0, "low": 0}

    hydration_status_counts: Counter[str] = Counter({"hydrated": 0, "not_hydrated": 0, "blocked": 0})
    hydration_by_source: Counter[str] = Counter()
    hydration_by_strategy: Counter[str] = Counter()
    hydration_by_channel: Counter[str] = Counter()
    hydration_by_reason: Counter[str] = Counter()
    hydration_total_events = 0
    graph_signal_presence_counts: Counter[str] = Counter()
    graph_signal_reason_counts: Counter[str] = Counter()
    graph_signal_true_counts: Counter[str] = Counter()
    graph_signal_total_events = 0
    graph_query_status_counts: Counter[str] = Counter()
    graph_query_relation_type_counts: Counter[str] = Counter()
    graph_query_reason_counts: Counter[str] = Counter()
    graph_query_ambiguity_count = 0
    graph_query_matched_id_total = 0
    graph_query_total_events = 0
    webview_total_with_diagnostics = 0
    webview_status_counts: Counter[str] = Counter()
    webview_recommended_context_counts: Counter[str] = Counter()
    webview_switch_required_future_count = 0
    webview_switch_attempted_count = 0
    webview_reason_counts: Counter[str] = Counter()
    webview_warning_counts: Counter[str] = Counter()
    system_dialog_total_with_detection = 0
    system_dialog_detected_count = 0
    system_dialog_type_counts: Counter[str] = Counter()
    system_dialog_platform_counts: Counter[str] = Counter()
    system_dialog_owner_counts: Counter[str] = Counter()
    system_dialog_recommended_action_counts: Counter[str] = Counter()
    system_dialog_warning_counts: Counter[str] = Counter()
    system_dialog_confidence_buckets = {"high": 0, "medium": 0, "low": 0}
    system_dialog_guardrails_total_with_guardrails = 0
    system_dialog_guardrails_decision_counts: Counter[str] = Counter()
    system_dialog_guardrails_reason_counts: Counter[str] = Counter()
    system_dialog_guardrails_dialog_type_counts: Counter[str] = Counter()
    system_dialog_guardrails_requested_action_counts: Counter[str] = Counter()
    system_dialog_guardrails_recommended_action_counts: Counter[str] = Counter()
    system_dialog_guardrails_opt_in_present_count = 0
    system_dialog_guardrails_action_attempted_count = 0
    system_dialog_guardrails_warning_counts: Counter[str] = Counter()
    system_dialog_action_total_with_metadata = 0
    system_dialog_action_candidate_found_count = 0
    system_dialog_action_attempted_count = 0
    system_dialog_action_status_counts: Counter[str] = Counter()
    system_dialog_action_reason_counts: Counter[str] = Counter()
    system_dialog_action_warning_counts: Counter[str] = Counter()
    scroll_discovery_total_with_metadata = 0
    scroll_discovery_needed_count = 0
    scroll_discovery_status_counts: Counter[str] = Counter()
    scroll_discovery_reason_counts: Counter[str] = Counter()
    scroll_discovery_platform_counts: Counter[str] = Counter()
    scroll_discovery_target_hint_type_counts: Counter[str] = Counter()
    scroll_discovery_direction_counts: Counter[str] = Counter()
    scroll_discovery_warning_counts: Counter[str] = Counter()
    scroll_discovery_max_scrolls_buckets = {"0": 0, "1-2": 0, "3-5": 0, "6+": 0}
    scroll_discovery_candidate_container_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    scroll_resolution_total_with_metadata = 0
    scroll_resolution_enabled_count = 0
    scroll_resolution_attempted_count = 0
    scroll_resolution_found_after_scroll_count = 0
    scroll_resolution_final_status_counts: Counter[str] = Counter()
    scroll_resolution_reason_counts: Counter[str] = Counter()
    scroll_resolution_warning_counts: Counter[str] = Counter()
    scroll_resolution_max_scrolls_buckets = {"0": 0, "1-2": 0, "3-5": 0, "6+": 0}
    scroll_resolution_attempt_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    repeated_region_total_with_metadata = 0
    repeated_region_status_counts: Counter[str] = Counter()
    repeated_region_type_counts: Counter[str] = Counter()
    repeated_region_reason_counts: Counter[str] = Counter()
    repeated_region_anchor_hint_type_counts: Counter[str] = Counter()
    repeated_region_target_action_hint_counts: Counter[str] = Counter()
    repeated_region_warning_counts: Counter[str] = Counter()
    repeated_region_matched_region_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    repeated_region_candidate_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    icon_detection_total_with_metadata = 0
    icon_detection_status_counts: Counter[str] = Counter()
    icon_detection_icon_hint_type_counts: Counter[str] = Counter()
    icon_detection_target_icon_counts: Counter[str] = Counter()
    icon_detection_reason_counts: Counter[str] = Counter()
    icon_detection_warning_counts: Counter[str] = Counter()
    icon_detection_candidate_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    icon_detection_matched_candidate_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    mobile_memory_signature_total_with_metadata = 0
    mobile_memory_signature_platform_counts: Counter[str] = Counter()
    mobile_memory_signature_surface_type_counts: Counter[str] = Counter()
    mobile_memory_signature_context_mode_counts: Counter[str] = Counter()
    mobile_memory_signature_dialog_state_counts: Counter[str] = Counter()
    mobile_memory_signature_scroll_state_counts: Counter[str] = Counter()
    mobile_memory_signature_repeated_region_status_counts: Counter[str] = Counter()
    mobile_memory_signature_icon_target_counts: Counter[str] = Counter()
    mobile_memory_signature_warning_counts: Counter[str] = Counter()
    cloud_provider_total_with_summary = 0
    cloud_provider_counts: Counter[str] = Counter()
    cloud_provider_namespace_counts: Counter[str] = Counter()
    cloud_platform_counts: Counter[str] = Counter()
    cloud_app_launch_strategy_counts: Counter[str] = Counter()
    cloud_url_source_counts: Counter[str] = Counter()
    cloud_automation_name_counts: Counter[str] = Counter()
    cloud_warning_counts: Counter[str] = Counter()
    webview_switch_eligibility_total = 0
    webview_switch_eligibility_decision_counts: Counter[str] = Counter()
    webview_switch_eligibility_reason_counts: Counter[str] = Counter()
    webview_switch_eligibility_instruction_hint_type_counts: Counter[str] = Counter()
    webview_switch_eligibility_opt_in_present_count = 0
    webview_switch_eligibility_diagnostics_candidate_count = 0
    webview_switch_eligibility_guardrails_allowed_count = 0
    webview_switch_eligibility_webview_context_available_count = 0
    webview_switch_eligibility_multi_webview_count = 0
    webview_switch_eligibility_system_dialog_blocking_count = 0
    webview_switch_eligibility_switch_attempted_count = 0
    webview_switch_eligibility_warning_counts: Counter[str] = Counter()
    webview_context_selection_total = 0
    webview_context_selection_decision_counts: Counter[str] = Counter()
    webview_context_selection_reason_counts: Counter[str] = Counter()
    webview_context_selection_selection_policy_counts: Counter[str] = Counter()
    webview_context_selection_selected_context_type_counts: Counter[str] = Counter()
    webview_context_selection_eligibility_decision_counts: Counter[str] = Counter()
    webview_context_selection_switch_attempted_count = 0
    webview_context_selection_warning_counts: Counter[str] = Counter()
    webview_context_selection_candidate_context_count_buckets = {"0": 0, "1": 0, "2-3": 0, "4+": 0}
    webview_switch_execution_total = 0
    webview_switch_execution_enabled_count = 0
    webview_switch_execution_attempted_count = 0
    webview_switch_execution_restore_attempted_count = 0
    webview_switch_execution_status_counts: Counter[str] = Counter()
    webview_switch_execution_restore_status_counts: Counter[str] = Counter()
    webview_switch_execution_original_context_type_counts: Counter[str] = Counter()
    webview_switch_execution_selected_context_type_counts: Counter[str] = Counter()
    webview_switch_execution_reason_counts: Counter[str] = Counter()
    webview_switch_execution_warning_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_total = 0
    webview_switch_wiring_plan_enabled_count = 0
    webview_switch_wiring_plan_switch_ready_count = 0
    webview_switch_wiring_plan_reason_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_operation_type_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_mode_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_eligibility_decision_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_context_selection_decision_counts: Counter[str] = Counter()
    webview_switch_wiring_plan_warning_counts: Counter[str] = Counter()

    for result in results:
        status_counts[result.status] += 1

        if result.target and result.target.resolver_name:
            resolver_win_counts[result.target.resolver_name] += 1

        if result.error and result.error.error_type:
            error_type_counts[result.error.error_type] += 1

        conf = float(result.confidence)
        confidences.append(conf)
        if conf >= 0.85:
            confidence_buckets["high"] += 1
        elif conf >= 0.70:
            confidence_buckets["medium"] += 1
        else:
            confidence_buckets["low"] += 1

        metadata = result.target.metadata if result.target else {}
        hydration = safe_hydration_metadata(metadata)
        graph_signals = safe_graph_signals_metadata(metadata)
        graph_query_diagnostics = safe_graph_query_diagnostics_metadata(metadata)
        webview_diagnostics = safe_webview_switch_diagnostics_metadata(metadata)
        webview_switch_eligibility = safe_webview_switch_eligibility_metadata(metadata)
        webview_context_selection = safe_webview_context_selection_metadata(metadata)
        webview_switch_execution = safe_webview_switch_execution_metadata(metadata)
        webview_switch_wiring_plan = safe_webview_switch_wiring_plan_metadata(metadata)
        system_dialog_detection = safe_system_dialog_detection_metadata(metadata)
        system_dialog_guardrails = safe_system_dialog_guardrails_metadata(metadata)
        system_dialog_action = safe_system_dialog_action_metadata(metadata)
        scroll_discovery = safe_scroll_discovery_metadata(metadata)
        scroll_resolution = safe_scroll_resolution_metadata(metadata)
        repeated_region = safe_repeated_region_diagnostics_metadata(metadata)
        icon_detection = safe_icon_detection_metadata(metadata)
        mobile_memory_signature = safe_mobile_memory_signature_metadata(metadata)
        cloud_provider_summary = safe_cloud_provider_summary_metadata(metadata)
        status = hydration.get("hydration_status")
        if isinstance(status, str) and status:
            hydration_total_events += 1
            if status in hydration_status_counts:
                hydration_status_counts[status] += 1
            _count_categorical_field(hydration_by_source, hydration.get("hydration_source"))
            _count_categorical_field(hydration_by_strategy, hydration.get("hydration_strategy"))
            _count_categorical_field(hydration_by_channel, hydration.get("hydration_channel"))
            _count_categorical_field(hydration_by_reason, hydration.get("hydration_reason"))
        if graph_signals:
            graph_signal_total_events += 1
            reason = graph_signals.get("reason")
            _count_categorical_field(graph_signal_reason_counts, reason)
            for key in _SAFE_GRAPH_SIGNAL_FIELDS:
                if key in graph_signals:
                    graph_signal_presence_counts[key] += 1
            for key, value in graph_signals.items():
                if isinstance(value, bool) and value:
                    graph_signal_true_counts[key] += 1
        if webview_diagnostics:
            webview_total_with_diagnostics += 1
            _count_categorical_field(webview_status_counts, webview_diagnostics.get("status"))
            _count_categorical_field(webview_recommended_context_counts, webview_diagnostics.get("recommended_context"))
            if webview_diagnostics.get("switch_required_future") is True:
                webview_switch_required_future_count += 1
            if webview_diagnostics.get("switch_attempted") is True:
                webview_switch_attempted_count += 1
            _count_categorical_field(webview_reason_counts, webview_diagnostics.get("reason"))
            warnings = webview_diagnostics.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(webview_warning_counts, warning)
        if webview_switch_eligibility:
            webview_switch_eligibility_total += 1
            _count_categorical_field(webview_switch_eligibility_decision_counts, webview_switch_eligibility.get("decision"))
            _count_categorical_field(webview_switch_eligibility_reason_counts, webview_switch_eligibility.get("reason"))
            _count_categorical_field(webview_switch_eligibility_instruction_hint_type_counts, webview_switch_eligibility.get("instruction_hint_type"))
            if webview_switch_eligibility.get("opt_in_present") is True:
                webview_switch_eligibility_opt_in_present_count += 1
            if webview_switch_eligibility.get("diagnostics_candidate") is True:
                webview_switch_eligibility_diagnostics_candidate_count += 1
            if webview_switch_eligibility.get("guardrails_allowed") is True:
                webview_switch_eligibility_guardrails_allowed_count += 1
            if webview_switch_eligibility.get("webview_context_available") is True:
                webview_switch_eligibility_webview_context_available_count += 1
            if webview_switch_eligibility.get("multi_webview") is True:
                webview_switch_eligibility_multi_webview_count += 1
            if webview_switch_eligibility.get("system_dialog_blocking") is True:
                webview_switch_eligibility_system_dialog_blocking_count += 1
            if webview_switch_eligibility.get("switch_attempted") is True:
                webview_switch_eligibility_switch_attempted_count += 1
            warnings = webview_switch_eligibility.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(webview_switch_eligibility_warning_counts, warning)
        if webview_context_selection:
            webview_context_selection_total += 1
            _count_categorical_field(webview_context_selection_decision_counts, webview_context_selection.get("decision"))
            _count_categorical_field(webview_context_selection_reason_counts, webview_context_selection.get("reason"))
            _count_categorical_field(webview_context_selection_selection_policy_counts, webview_context_selection.get("selection_policy"))
            _count_categorical_field(webview_context_selection_selected_context_type_counts, webview_context_selection.get("selected_context_type"))
            _count_categorical_field(webview_context_selection_eligibility_decision_counts, webview_context_selection.get("eligibility_decision"))
            if webview_context_selection.get("switch_attempted") is True:
                webview_context_selection_switch_attempted_count += 1
            warnings = webview_context_selection.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(webview_context_selection_warning_counts, warning)
            c = webview_context_selection.get("candidate_context_count")
            if isinstance(c, int):
                if c <= 0:
                    webview_context_selection_candidate_context_count_buckets["0"] += 1
                elif c == 1:
                    webview_context_selection_candidate_context_count_buckets["1"] += 1
                elif c <= 3:
                    webview_context_selection_candidate_context_count_buckets["2-3"] += 1
                else:
                    webview_context_selection_candidate_context_count_buckets["4+"] += 1
        if webview_switch_execution:
            webview_switch_execution_total += 1
            if webview_switch_execution.get("switch_enabled") is True:
                webview_switch_execution_enabled_count += 1
            if webview_switch_execution.get("switch_attempted") is True:
                webview_switch_execution_attempted_count += 1
            if webview_switch_execution.get("restore_attempted") is True:
                webview_switch_execution_restore_attempted_count += 1
            _count_categorical_field(webview_switch_execution_status_counts, webview_switch_execution.get("switch_status"))
            _count_categorical_field(webview_switch_execution_restore_status_counts, webview_switch_execution.get("restore_status"))
            _count_categorical_field(webview_switch_execution_original_context_type_counts, webview_switch_execution.get("original_context_type"))
            _count_categorical_field(webview_switch_execution_selected_context_type_counts, webview_switch_execution.get("selected_context_type"))
            _count_categorical_field(webview_switch_execution_reason_counts, webview_switch_execution.get("reason"))
            warnings = webview_switch_execution.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(webview_switch_execution_warning_counts, warning)
        if webview_switch_wiring_plan:
            webview_switch_wiring_plan_total += 1
            if webview_switch_wiring_plan.get("enabled") is True:
                webview_switch_wiring_plan_enabled_count += 1
            if webview_switch_wiring_plan.get("switch_ready") is True:
                webview_switch_wiring_plan_switch_ready_count += 1
            _count_categorical_field(webview_switch_wiring_plan_reason_counts, webview_switch_wiring_plan.get("reason"))
            _count_categorical_field(webview_switch_wiring_plan_operation_type_counts, webview_switch_wiring_plan.get("operation_type"))
            _count_categorical_field(webview_switch_wiring_plan_mode_counts, webview_switch_wiring_plan.get("mode"))
            _count_categorical_field(webview_switch_wiring_plan_eligibility_decision_counts, webview_switch_wiring_plan.get("eligibility_decision"))
            _count_categorical_field(webview_switch_wiring_plan_context_selection_decision_counts, webview_switch_wiring_plan.get("context_selection_decision"))
            warnings = webview_switch_wiring_plan.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(webview_switch_wiring_plan_warning_counts, warning)
        if system_dialog_detection:
            system_dialog_total_with_detection += 1
            if system_dialog_detection.get("dialog_detected") is True:
                system_dialog_detected_count += 1
            _count_categorical_field(system_dialog_type_counts, system_dialog_detection.get("dialog_type"))
            _count_categorical_field(system_dialog_platform_counts, system_dialog_detection.get("platform"))
            _count_categorical_field(system_dialog_owner_counts, system_dialog_detection.get("owner"))
            _count_categorical_field(system_dialog_recommended_action_counts, system_dialog_detection.get("recommended_action"))
            warnings = system_dialog_detection.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(system_dialog_warning_counts, warning)
            conf = system_dialog_detection.get("confidence")
            if isinstance(conf, (int, float)):
                if conf >= 0.85:
                    system_dialog_confidence_buckets["high"] += 1
                elif conf >= 0.70:
                    system_dialog_confidence_buckets["medium"] += 1
                else:
                    system_dialog_confidence_buckets["low"] += 1
        if system_dialog_guardrails:
            system_dialog_guardrails_total_with_guardrails += 1
            _count_categorical_field(system_dialog_guardrails_decision_counts, system_dialog_guardrails.get("decision"))
            _count_categorical_field(system_dialog_guardrails_reason_counts, system_dialog_guardrails.get("reason"))
            _count_categorical_field(system_dialog_guardrails_dialog_type_counts, system_dialog_guardrails.get("dialog_type"))
            _count_categorical_field(system_dialog_guardrails_requested_action_counts, system_dialog_guardrails.get("requested_action"))
            _count_categorical_field(system_dialog_guardrails_recommended_action_counts, system_dialog_guardrails.get("recommended_action"))
            if system_dialog_guardrails.get("opt_in_present") is True:
                system_dialog_guardrails_opt_in_present_count += 1
            if system_dialog_guardrails.get("action_attempted") is True:
                system_dialog_guardrails_action_attempted_count += 1
            warnings = system_dialog_guardrails.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(system_dialog_guardrails_warning_counts, warning)
        if system_dialog_action:
            system_dialog_action_total_with_metadata += 1
            if system_dialog_action.get("candidate_found") is True:
                system_dialog_action_candidate_found_count += 1
            if system_dialog_action.get("action_attempted") is True:
                system_dialog_action_attempted_count += 1
            _count_categorical_field(system_dialog_action_status_counts, system_dialog_action.get("action_status"))
            _count_categorical_field(system_dialog_action_reason_counts, system_dialog_action.get("reason"))
            warnings = system_dialog_action.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(system_dialog_action_warning_counts, warning)
        if scroll_discovery:
            scroll_discovery_total_with_metadata += 1
            if scroll_discovery.get("scroll_needed") is True:
                scroll_discovery_needed_count += 1
            _count_categorical_field(scroll_discovery_status_counts, scroll_discovery.get("status"))
            _count_categorical_field(scroll_discovery_reason_counts, scroll_discovery.get("reason"))
            _count_categorical_field(scroll_discovery_platform_counts, scroll_discovery.get("platform"))
            _count_categorical_field(scroll_discovery_target_hint_type_counts, scroll_discovery.get("target_hint_type"))
            _count_categorical_field(scroll_discovery_direction_counts, scroll_discovery.get("scroll_direction"))
            warnings = scroll_discovery.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(scroll_discovery_warning_counts, warning)
            max_scrolls = scroll_discovery.get("max_scrolls")
            if isinstance(max_scrolls, int):
                if max_scrolls <= 0:
                    scroll_discovery_max_scrolls_buckets["0"] += 1
                elif max_scrolls <= 2:
                    scroll_discovery_max_scrolls_buckets["1-2"] += 1
                elif max_scrolls <= 5:
                    scroll_discovery_max_scrolls_buckets["3-5"] += 1
                else:
                    scroll_discovery_max_scrolls_buckets["6+"] += 1
            container_count = scroll_discovery.get("candidate_container_count")
            if isinstance(container_count, int):
                if container_count <= 0:
                    scroll_discovery_candidate_container_count_buckets["0"] += 1
                elif container_count == 1:
                    scroll_discovery_candidate_container_count_buckets["1"] += 1
                elif container_count <= 3:
                    scroll_discovery_candidate_container_count_buckets["2-3"] += 1
                else:
                    scroll_discovery_candidate_container_count_buckets["4+"] += 1

        if mobile_memory_signature:
            mobile_memory_signature_total_with_metadata += 1
            _count_categorical_field(mobile_memory_signature_platform_counts, mobile_memory_signature.get("platform"))
            _count_categorical_field(mobile_memory_signature_surface_type_counts, mobile_memory_signature.get("surface_type"))
            _count_categorical_field(mobile_memory_signature_context_mode_counts, mobile_memory_signature.get("context_mode"))
            _count_categorical_field(mobile_memory_signature_dialog_state_counts, mobile_memory_signature.get("dialog_state"))
            _count_categorical_field(mobile_memory_signature_scroll_state_counts, mobile_memory_signature.get("scroll_state"))
            _count_categorical_field(mobile_memory_signature_repeated_region_status_counts, mobile_memory_signature.get("repeated_region_status"))
            _count_categorical_field(mobile_memory_signature_icon_target_counts, mobile_memory_signature.get("icon_target"))
            warnings = mobile_memory_signature.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(mobile_memory_signature_warning_counts, warning)
        if cloud_provider_summary:
            cloud_provider_total_with_summary += 1
            _count_categorical_field(cloud_provider_counts, cloud_provider_summary.get("provider"))
            _count_categorical_field(cloud_provider_namespace_counts, cloud_provider_summary.get("provider_namespace"))
            _count_categorical_field(cloud_platform_counts, cloud_provider_summary.get("platform"))
            _count_categorical_field(cloud_app_launch_strategy_counts, cloud_provider_summary.get("app_launch_strategy"))
            _count_categorical_field(cloud_url_source_counts, cloud_provider_summary.get("url_source"))
            _count_categorical_field(cloud_automation_name_counts, cloud_provider_summary.get("automation_name"))
            warnings = cloud_provider_summary.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(cloud_warning_counts, warning)

        if repeated_region:
            repeated_region_total_with_metadata += 1
            _count_categorical_field(repeated_region_status_counts, repeated_region.get("status"))
            _count_categorical_field(repeated_region_type_counts, repeated_region.get("region_type"))
            _count_categorical_field(repeated_region_reason_counts, repeated_region.get("reason"))
            _count_categorical_field(repeated_region_anchor_hint_type_counts, repeated_region.get("anchor_hint_type"))
            _count_categorical_field(repeated_region_target_action_hint_counts, repeated_region.get("target_action_hint"))
            warnings = repeated_region.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(repeated_region_warning_counts, warning)
            matched_region_count = repeated_region.get("matched_region_count")
            if isinstance(matched_region_count, int):
                if matched_region_count <= 0:
                    repeated_region_matched_region_count_buckets["0"] += 1
                elif matched_region_count == 1:
                    repeated_region_matched_region_count_buckets["1"] += 1
                elif matched_region_count <= 3:
                    repeated_region_matched_region_count_buckets["2-3"] += 1
                else:
                    repeated_region_matched_region_count_buckets["4+"] += 1
            candidate_count = repeated_region.get("candidate_count")
            if isinstance(candidate_count, int):
                if candidate_count <= 0:
                    repeated_region_candidate_count_buckets["0"] += 1
                elif candidate_count == 1:
                    repeated_region_candidate_count_buckets["1"] += 1
                elif candidate_count <= 3:
                    repeated_region_candidate_count_buckets["2-3"] += 1
                else:
                    repeated_region_candidate_count_buckets["4+"] += 1
        if icon_detection:
            icon_detection_total_with_metadata += 1
            _count_categorical_field(icon_detection_status_counts, icon_detection.get("status"))
            _count_categorical_field(icon_detection_icon_hint_type_counts, icon_detection.get("icon_hint_type"))
            _count_categorical_field(icon_detection_target_icon_counts, icon_detection.get("target_icon"))
            _count_categorical_field(icon_detection_reason_counts, icon_detection.get("reason"))
            warnings = icon_detection.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(icon_detection_warning_counts, warning)
            candidate_count = icon_detection.get("candidate_count")
            if isinstance(candidate_count, int):
                if candidate_count <= 0:
                    icon_detection_candidate_count_buckets["0"] += 1
                elif candidate_count == 1:
                    icon_detection_candidate_count_buckets["1"] += 1
                elif candidate_count <= 3:
                    icon_detection_candidate_count_buckets["2-3"] += 1
                else:
                    icon_detection_candidate_count_buckets["4+"] += 1
            matched_candidate_count = icon_detection.get("matched_candidate_count")
            if isinstance(matched_candidate_count, int):
                if matched_candidate_count <= 0:
                    icon_detection_matched_candidate_count_buckets["0"] += 1
                elif matched_candidate_count == 1:
                    icon_detection_matched_candidate_count_buckets["1"] += 1
                elif matched_candidate_count <= 3:
                    icon_detection_matched_candidate_count_buckets["2-3"] += 1
                else:
                    icon_detection_matched_candidate_count_buckets["4+"] += 1
        if scroll_resolution:
            scroll_resolution_total_with_metadata += 1
            if scroll_resolution.get("enabled") is True:
                scroll_resolution_enabled_count += 1
            if scroll_resolution.get("attempted") is True:
                scroll_resolution_attempted_count += 1
            if scroll_resolution.get("found_after_scroll") is True:
                scroll_resolution_found_after_scroll_count += 1
            _count_categorical_field(scroll_resolution_final_status_counts, scroll_resolution.get("final_status"))
            _count_categorical_field(scroll_resolution_reason_counts, scroll_resolution.get("reason"))
            warnings = scroll_resolution.get("warnings")
            if isinstance(warnings, list):
                for warning in warnings:
                    _count_categorical_field(scroll_resolution_warning_counts, warning)
            max_scrolls = scroll_resolution.get("max_scrolls")
            if isinstance(max_scrolls, int):
                if max_scrolls <= 0:
                    scroll_resolution_max_scrolls_buckets["0"] += 1
                elif max_scrolls <= 2:
                    scroll_resolution_max_scrolls_buckets["1-2"] += 1
                elif max_scrolls <= 5:
                    scroll_resolution_max_scrolls_buckets["3-5"] += 1
                else:
                    scroll_resolution_max_scrolls_buckets["6+"] += 1
            attempt_count = scroll_resolution.get("attempt_count")
            if isinstance(attempt_count, int):
                if attempt_count <= 0:
                    scroll_resolution_attempt_count_buckets["0"] += 1
                elif attempt_count == 1:
                    scroll_resolution_attempt_count_buckets["1"] += 1
                elif attempt_count <= 3:
                    scroll_resolution_attempt_count_buckets["2-3"] += 1
                else:
                    scroll_resolution_attempt_count_buckets["4+"] += 1

        if graph_query_diagnostics:
            graph_query_total_events += 1
            _count_categorical_field(graph_query_status_counts, graph_query_diagnostics.get("status"))
            _count_categorical_field(graph_query_relation_type_counts, graph_query_diagnostics.get("relation_type"))
            if graph_query_diagnostics.get("ambiguity") is True:
                graph_query_ambiguity_count += 1
            reasons = graph_query_diagnostics.get("reasons")
            if isinstance(reasons, list):
                for reason in reasons:
                    _count_categorical_field(graph_query_reason_counts, reason)
            matched_ids = graph_query_diagnostics.get("matched_ids")
            if isinstance(matched_ids, list):
                graph_query_matched_id_total += len(matched_ids)

    conf_count = len(confidences)
    confidence_summary = {
        "count": conf_count,
        "min": min(confidences) if confidences else None,
        "max": max(confidences) if confidences else None,
        "average": (sum(confidences) / conf_count) if conf_count else None,
        "buckets": confidence_buckets,
    }
    hydration_summary = {
        "total_events": hydration_total_events,
        "status_counts": dict(hydration_status_counts),
        "by_source": dict(hydration_by_source),
        "by_strategy": dict(hydration_by_strategy),
        "by_channel": dict(hydration_by_channel),
        "by_reason": dict(hydration_by_reason),
    }
    graph_signal_summary = {
        "total_events": graph_signal_total_events,
        "presence_counts": dict(graph_signal_presence_counts),
        "reason_counts": dict(graph_signal_reason_counts),
        "field_true_counts": dict(graph_signal_true_counts),
    }

    webview_diagnostics_summary = {
        "total_with_diagnostics": webview_total_with_diagnostics,
        "status_counts": dict(webview_status_counts),
        "recommended_context_counts": dict(webview_recommended_context_counts),
        "switch_required_future_count": webview_switch_required_future_count,
        "switch_attempted_count": webview_switch_attempted_count,
        "reason_counts": dict(webview_reason_counts),
        "warning_counts": dict(webview_warning_counts),
    }


    webview_switch_eligibility_summary = {
        "total_with_eligibility": webview_switch_eligibility_total,
        "decision_counts": dict(webview_switch_eligibility_decision_counts),
        "reason_counts": dict(webview_switch_eligibility_reason_counts),
        "instruction_hint_type_counts": dict(webview_switch_eligibility_instruction_hint_type_counts),
        "opt_in_present_count": webview_switch_eligibility_opt_in_present_count,
        "diagnostics_candidate_count": webview_switch_eligibility_diagnostics_candidate_count,
        "guardrails_allowed_count": webview_switch_eligibility_guardrails_allowed_count,
        "webview_context_available_count": webview_switch_eligibility_webview_context_available_count,
        "multi_webview_count": webview_switch_eligibility_multi_webview_count,
        "system_dialog_blocking_count": webview_switch_eligibility_system_dialog_blocking_count,
        "switch_attempted_count": webview_switch_eligibility_switch_attempted_count,
        "warning_counts": dict(webview_switch_eligibility_warning_counts),
    }
    webview_context_selection_summary = {
        "total_with_context_selection": webview_context_selection_total,
        "decision_counts": dict(webview_context_selection_decision_counts),
        "reason_counts": dict(webview_context_selection_reason_counts),
        "selection_policy_counts": dict(webview_context_selection_selection_policy_counts),
        "selected_context_type_counts": dict(webview_context_selection_selected_context_type_counts),
        "eligibility_decision_counts": dict(webview_context_selection_eligibility_decision_counts),
        "switch_attempted_count": webview_context_selection_switch_attempted_count,
        "warning_counts": dict(webview_context_selection_warning_counts),
        "candidate_context_count_buckets": dict(webview_context_selection_candidate_context_count_buckets),
    }
    webview_switch_execution_summary = {
        "total_with_switch_execution": webview_switch_execution_total,
        "switch_enabled_count": webview_switch_execution_enabled_count,
        "switch_attempted_count": webview_switch_execution_attempted_count,
        "restore_attempted_count": webview_switch_execution_restore_attempted_count,
        "switch_status_counts": dict(webview_switch_execution_status_counts),
        "restore_status_counts": dict(webview_switch_execution_restore_status_counts),
        "original_context_type_counts": dict(webview_switch_execution_original_context_type_counts),
        "selected_context_type_counts": dict(webview_switch_execution_selected_context_type_counts),
        "reason_counts": dict(webview_switch_execution_reason_counts),
        "warning_counts": dict(webview_switch_execution_warning_counts),
    }

    webview_switch_wiring_plan_summary = {
        "total_with_wiring_plan": webview_switch_wiring_plan_total,
        "enabled_count": webview_switch_wiring_plan_enabled_count,
        "switch_ready_count": webview_switch_wiring_plan_switch_ready_count,
        "reason_counts": dict(webview_switch_wiring_plan_reason_counts),
        "operation_type_counts": dict(webview_switch_wiring_plan_operation_type_counts),
        "mode_counts": dict(webview_switch_wiring_plan_mode_counts),
        "eligibility_decision_counts": dict(webview_switch_wiring_plan_eligibility_decision_counts),
        "context_selection_decision_counts": dict(webview_switch_wiring_plan_context_selection_decision_counts),
        "warning_counts": dict(webview_switch_wiring_plan_warning_counts),
    }

    system_dialog_summary = {
        "total_with_detection": system_dialog_total_with_detection,
        "detected_count": system_dialog_detected_count,
        "dialog_type_counts": dict(system_dialog_type_counts),
        "platform_counts": dict(system_dialog_platform_counts),
        "owner_counts": dict(system_dialog_owner_counts),
        "recommended_action_counts": dict(system_dialog_recommended_action_counts),
        "warning_counts": dict(system_dialog_warning_counts),
        "confidence_buckets": dict(system_dialog_confidence_buckets),
    }
    system_dialog_guardrails_summary = {
        "total_with_guardrails": system_dialog_guardrails_total_with_guardrails,
        "decision_counts": dict(system_dialog_guardrails_decision_counts),
        "reason_counts": dict(system_dialog_guardrails_reason_counts),
        "dialog_type_counts": dict(system_dialog_guardrails_dialog_type_counts),
        "requested_action_counts": dict(system_dialog_guardrails_requested_action_counts),
        "recommended_action_counts": dict(system_dialog_guardrails_recommended_action_counts),
        "opt_in_present_count": system_dialog_guardrails_opt_in_present_count,
        "action_attempted_count": system_dialog_guardrails_action_attempted_count,
        "warning_counts": dict(system_dialog_guardrails_warning_counts),
    }
    system_dialog_action_summary = {
        "total_with_action_metadata": system_dialog_action_total_with_metadata,
        "candidate_found_count": system_dialog_action_candidate_found_count,
        "action_attempted_count": system_dialog_action_attempted_count,
        "action_status_counts": dict(system_dialog_action_status_counts),
        "reason_counts": dict(system_dialog_action_reason_counts),
        "warning_counts": dict(system_dialog_action_warning_counts),
    }
    scroll_discovery_summary = {
        "total_with_scroll_discovery": scroll_discovery_total_with_metadata,
        "scroll_needed_count": scroll_discovery_needed_count,
        "status_counts": dict(scroll_discovery_status_counts),
        "reason_counts": dict(scroll_discovery_reason_counts),
        "platform_counts": dict(scroll_discovery_platform_counts),
        "target_hint_type_counts": dict(scroll_discovery_target_hint_type_counts),
        "scroll_direction_counts": dict(scroll_discovery_direction_counts),
        "warning_counts": dict(scroll_discovery_warning_counts),
        "max_scrolls_buckets": dict(scroll_discovery_max_scrolls_buckets),
        "candidate_container_count_buckets": dict(scroll_discovery_candidate_container_count_buckets),
    }

    repeated_region_summary = {
        "total_with_repeated_region_diagnostics": repeated_region_total_with_metadata,
        "status_counts": dict(repeated_region_status_counts),
        "region_type_counts": dict(repeated_region_type_counts),
        "reason_counts": dict(repeated_region_reason_counts),
        "anchor_hint_type_counts": dict(repeated_region_anchor_hint_type_counts),
        "target_action_hint_counts": dict(repeated_region_target_action_hint_counts),
        "warning_counts": dict(repeated_region_warning_counts),
        "matched_region_count_buckets": dict(repeated_region_matched_region_count_buckets),
        "candidate_count_buckets": dict(repeated_region_candidate_count_buckets),
    }

    scroll_resolution_summary = {
        "total_with_scroll_resolution": scroll_resolution_total_with_metadata,
        "enabled_count": scroll_resolution_enabled_count,
        "attempted_count": scroll_resolution_attempted_count,
        "found_after_scroll_count": scroll_resolution_found_after_scroll_count,
        "final_status_counts": dict(scroll_resolution_final_status_counts),
        "reason_counts": dict(scroll_resolution_reason_counts),
        "warning_counts": dict(scroll_resolution_warning_counts),
        "max_scrolls_buckets": dict(scroll_resolution_max_scrolls_buckets),
        "attempt_count_buckets": dict(scroll_resolution_attempt_count_buckets),
    }

    mobile_memory_signature_summary = {
        "total_with_mobile_memory_signature": mobile_memory_signature_total_with_metadata,
        "platform_counts": dict(mobile_memory_signature_platform_counts),
        "surface_type_counts": dict(mobile_memory_signature_surface_type_counts),
        "context_mode_counts": dict(mobile_memory_signature_context_mode_counts),
        "dialog_state_counts": dict(mobile_memory_signature_dialog_state_counts),
        "scroll_state_counts": dict(mobile_memory_signature_scroll_state_counts),
        "repeated_region_status_counts": dict(mobile_memory_signature_repeated_region_status_counts),
        "icon_target_counts": dict(mobile_memory_signature_icon_target_counts),
        "warning_counts": dict(mobile_memory_signature_warning_counts),
    }

    icon_detection_summary = {
        "total_with_icon_detection": icon_detection_total_with_metadata,
        "status_counts": dict(icon_detection_status_counts),
        "icon_hint_type_counts": dict(icon_detection_icon_hint_type_counts),
        "target_icon_counts": dict(icon_detection_target_icon_counts),
        "reason_counts": dict(icon_detection_reason_counts),
        "warning_counts": dict(icon_detection_warning_counts),
        "candidate_count_buckets": dict(icon_detection_candidate_count_buckets),
        "matched_candidate_count_buckets": dict(icon_detection_matched_candidate_count_buckets),
    }
    cloud_provider_summary_analytics = {
        "total_with_cloud_provider_summary": cloud_provider_total_with_summary,
        "provider_counts": dict(cloud_provider_counts),
        "provider_namespace_counts": dict(cloud_provider_namespace_counts),
        "platform_counts": dict(cloud_platform_counts),
        "app_launch_strategy_counts": dict(cloud_app_launch_strategy_counts),
        "url_source_counts": dict(cloud_url_source_counts),
        "automation_name_counts": dict(cloud_automation_name_counts),
        "warning_counts": dict(cloud_warning_counts),
    }

    graph_query_summary = {
        "total_events": graph_query_total_events,
        "status_counts": dict(graph_query_status_counts),
        "relation_type_counts": dict(graph_query_relation_type_counts),
        "ambiguity_count": graph_query_ambiguity_count,
        "reason_counts": dict(graph_query_reason_counts),
        "matched_id_total": graph_query_matched_id_total,
    }

    return {
        "total": len(results),
        "status_counts": dict(status_counts),
        "resolver_win_counts": dict(resolver_win_counts),
        "confidence_summary": confidence_summary,
        "error_type_counts": dict(error_type_counts),
        "hydration_summary": hydration_summary,
        "graph_signal_summary": graph_signal_summary,
        "graph_query_summary": graph_query_summary,
        "webview_diagnostics_summary": webview_diagnostics_summary,
        "webview_switch_eligibility_summary": webview_switch_eligibility_summary,
        "webview_context_selection_summary": webview_context_selection_summary,
        "webview_switch_execution_summary": webview_switch_execution_summary,
        "webview_switch_wiring_plan_summary": webview_switch_wiring_plan_summary,
        "system_dialog_summary": system_dialog_summary,
        "system_dialog_guardrails_summary": system_dialog_guardrails_summary,
        "system_dialog_action_summary": system_dialog_action_summary,
        "scroll_discovery_summary": scroll_discovery_summary,
        "scroll_resolution_summary": scroll_resolution_summary,
        "repeated_region_summary": repeated_region_summary,
        "mobile_memory_signature_summary": mobile_memory_signature_summary,
        "icon_detection_summary": icon_detection_summary,
        "cloud_provider_summary": cloud_provider_summary_analytics,
    }
