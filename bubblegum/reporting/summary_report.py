"""
bubblegum/reporting/summary_report.py
=====================================
Cross-run suite summary (a54).

The per-format reports (html/json/junit/allure) are written per **session**
(per process), so when several tests each run in their own process and write to
the same paths, only the last one survives. This module keeps a small **manifest**
that each run **upserts** into (keyed by ``suite_name``), plus an HTML overview,
so a suite of independently-run tests shows one aggregated page: which tests ran,
each test's pass/fail/skip, and grand totals.

Usage (per test run, via the bridge / TS ``report({ summary, suiteName })``):
    write_summary(results, "reports/bubblegum-summary.html",
                  suite_name="EDSH Challenge Creation")

Re-running a test with the same ``suite_name`` replaces its row, so the manifest
always reflects the latest result of each named test. Delete the sibling
``*.json`` manifest to reset the suite.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult

_MANIFEST_VERSION = 2
# A step is "successful" for test-level status if it passed or self-healed.
_PASS_STATUSES = {"passed", "recovered"}


def _count_statuses(results: Sequence[StepResult]) -> dict[str, int]:
    counts = {"passed": 0, "recovered": 0, "failed": 0, "skipped": 0, "dry_run": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def compute_run_summary(results: Sequence[StepResult], suite_name: str) -> dict:
    """Build one test's summary record from its StepResults."""
    counts = _count_statuses(results)
    total = len(results)
    duration_ms = sum(int(getattr(r, "duration_ms", 0) or 0) for r in results)
    # A test fails if any step failed; otherwise it passed (dry-run/skipped-only
    # runs count as passed — nothing failed).
    status = "failed" if counts["failed"] > 0 else "passed"
    return {
        "name": suite_name or "bubblegum",
        "status": status,
        "total": total,
        "passed": counts["passed"],
        "recovered": counts["recovered"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "dry_run": counts["dry_run"],
        "duration_ms": duration_ms,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }


def _manifest_path(html_path: Path) -> Path:
    return html_path.with_suffix(".json")


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": _MANIFEST_VERSION, "runs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:  # noqa: BLE001 — a corrupt manifest starts fresh, never breaks a run
        pass
    return {"version": _MANIFEST_VERSION, "runs": []}


def _upsert(runs: list[dict], record: dict) -> list[dict]:
    """Replace the run with the same name, else append. Preserves order."""
    out = [r for r in runs if r.get("name") != record["name"]]
    out.append(record)
    out.sort(key=lambda r: str(r.get("name", "")).lower())
    return out


def write_summary(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum-summary.html",
    *,
    suite_name: str = "bubblegum",
    title: str = "Bubblegum Suite Summary",
) -> Path:
    """Upsert this run into the suite manifest and (re)render the HTML overview."""
    html_path = Path(path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path(html_path)

    manifest = _load_manifest(manifest_path)
    manifest["version"] = _MANIFEST_VERSION
    manifest["runs"] = _upsert(manifest["runs"], compute_run_summary(results, suite_name))
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    html_path.write_text(_render_html(manifest, title), encoding="utf-8")
    return html_path.resolve()


# ---------------------------------------------------------------------------
# HTML rendering (self-contained, no external assets)
# ---------------------------------------------------------------------------

def _totals(runs: list[dict]) -> dict:
    t = {
        "tests": len(runs),
        "tests_passed": sum(1 for r in runs if r.get("status") == "passed"),
        "tests_failed": sum(1 for r in runs if r.get("status") == "failed"),
        "steps": sum(int(r.get("total", 0)) for r in runs),
        "passed": sum(int(r.get("passed", 0)) for r in runs),
        "recovered": sum(int(r.get("recovered", 0)) for r in runs),
        "failed": sum(int(r.get("failed", 0)) for r in runs),
        "skipped": sum(int(r.get("skipped", 0)) for r in runs),
        "dry_run": sum(int(r.get("dry_run", 0)) for r in runs),
    }
    return t


def _fmt_duration(ms: int) -> str:
    s = ms / 1000.0
    if s < 60:
        return f"{s:.1f}s"
    return f"{int(s // 60)}m {int(s % 60)}s"


def _render_html(manifest: dict, title: str) -> str:
    runs = manifest.get("runs", [])
    t = _totals(runs)
    generated = manifest.get("generated_at", "")

    rows = []
    for r in runs:
        status = r.get("status", "passed")
        badge = "PASS" if status == "passed" else "FAIL"
        recovered = int(r.get("recovered", 0))
        rows.append(
            "<tr class='{cls}'>"
            "<td class='name'>{name}</td>"
            "<td><span class='badge {cls}'>{badge}</span></td>"
            "<td class='num'>{total}</td>"
            "<td class='num pass'>{passed}</td>"
            "<td class='num heal'>{recovered}</td>"
            "<td class='num fail'>{failed}</td>"
            "<td class='num skip'>{skipped}</td>"
            "<td class='num'>{dur}</td>"
            "<td class='ts'>{ts}</td>"
            "</tr>".format(
                cls="failed" if status == "failed" else "passed",
                name=html.escape(str(r.get("name", ""))),
                badge=badge,
                total=int(r.get("total", 0)),
                passed=int(r.get("passed", 0)),
                recovered=recovered,
                failed=int(r.get("failed", 0)),
                skipped=int(r.get("skipped", 0)),
                dur=_fmt_duration(int(r.get("duration_ms", 0))),
                ts=html.escape(str(r.get("last_run", ""))[:19].replace("T", " ")),
            )
        )
    rows_html = "\n".join(rows) or "<tr><td colspan='9' class='empty'>No test runs recorded yet.</td></tr>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; padding: 24px; background: #f6f7f9; color: #1c2430; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #6b7280; font-size: 12px; margin-bottom: 20px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 16px; min-width: 96px; }}
  .card .k {{ font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }}
  .card .v {{ font-size: 22px; font-weight: 700; margin-top: 2px; }}
  .v.pass {{ color: #15803d; }} .v.fail {{ color: #b91c1c; }} .v.heal {{ color: #b45309; }} .v.skip {{ color: #6b7280; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f1f3; font-size: 13px; }}
  th {{ background: #fafbfc; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.name {{ font-weight: 600; }}
  td.pass {{ color: #15803d; }} td.heal {{ color: #b45309; }} td.fail {{ color: #b91c1c; }} td.skip {{ color: #9ca3af; }}
  td.ts {{ color: #6b7280; font-variant-numeric: tabular-nums; }}
  tr.failed td.name {{ color: #b91c1c; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }}
  .badge.passed {{ background: #dcfce7; color: #15803d; }}
  .badge.failed {{ background: #fee2e2; color: #b91c1c; }}
  .empty {{ text-align: center; color: #9ca3af; padding: 24px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f1115; color: #e5e7eb; }}
    .card, table {{ background: #171a21; border-color: #2a2f3a; }}
    th {{ background: #12151b; }} td, th {{ border-color: #232833; }}
  }}
</style></head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="sub">Generated {html.escape(str(generated)[:19].replace("T", " "))} · {t['tests']} test(s)</div>
  <div class="cards">
    <div class="card"><div class="k">Tests</div><div class="v">{t['tests']}</div></div>
    <div class="card"><div class="k">Tests Passed</div><div class="v pass">{t['tests_passed']}</div></div>
    <div class="card"><div class="k">Tests Failed</div><div class="v fail">{t['tests_failed']}</div></div>
    <div class="card"><div class="k">Total Steps</div><div class="v">{t['steps']}</div></div>
    <div class="card"><div class="k">Steps Passed</div><div class="v pass">{t['passed']}</div></div>
    <div class="card"><div class="k">Self-healed</div><div class="v heal">{t['recovered']}</div></div>
    <div class="card"><div class="k">Steps Failed</div><div class="v fail">{t['failed']}</div></div>
    <div class="card"><div class="k">Skipped</div><div class="v skip">{t['skipped']}</div></div>
  </div>
  <table>
    <thead><tr>
      <th>Test</th><th>Status</th><th class="num">Steps</th><th class="num">Passed</th>
      <th class="num">Healed</th><th class="num">Failed</th><th class="num">Skipped</th>
      <th class="num">Duration</th><th>Last Run</th>
    </tr></thead>
    <tbody>
{rows_html}
    </tbody>
  </table>
</body></html>"""
