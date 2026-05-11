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
    return {k: v for k, v in metadata.items() if k not in _UNSAFE_HYDRATION_KEYS and k not in _UNSAFE_RETRY_KEYS and k not in _UNSAFE_WAIT_KEYS}


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

    return {
        "total": len(results),
        "status_counts": dict(status_counts),
        "resolver_win_counts": dict(resolver_win_counts),
        "confidence_summary": confidence_summary,
        "error_type_counts": dict(error_type_counts),
        "hydration_summary": hydration_summary,
        "graph_signal_summary": graph_signal_summary,
    }
