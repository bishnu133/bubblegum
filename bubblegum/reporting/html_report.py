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


def build_report_analytics(results: Sequence[StepResult]) -> dict:
    """
    Build aggregate analytics for a list of StepResult objects.

    Returned structure:
      - total
      - status_counts
      - resolver_win_counts
      - confidence_summary {count,min,max,average,buckets}
      - error_type_counts
    """
    status_counts = Counter(
        {"passed": 0, "recovered": 0, "failed": 0, "skipped": 0}
    )
    resolver_win_counts: Counter[str] = Counter()
    error_type_counts: Counter[str] = Counter()

    confidences: list[float] = []
    confidence_buckets = {"high": 0, "medium": 0, "low": 0}

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

    conf_count = len(confidences)
    confidence_summary = {
        "count": conf_count,
        "min": min(confidences) if confidences else None,
        "max": max(confidences) if confidences else None,
        "average": (sum(confidences) / conf_count) if conf_count else None,
        "buckets": confidence_buckets,
    }

    return {
        "total": len(results),
        "status_counts": dict(status_counts),
        "resolver_win_counts": dict(resolver_win_counts),
        "confidence_summary": confidence_summary,
        "error_type_counts": dict(error_type_counts),
    }
