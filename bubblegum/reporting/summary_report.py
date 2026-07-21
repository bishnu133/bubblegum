"""
bubblegum/reporting/summary_report.py
=====================================
Combined suite report (a54 summary, a55 combined detail).

The per-format reports (html/json/junit/allure) are written per **session** (per
process), so when several tests each run in their own process and write to the
same paths, only the last one survives. This module produces ONE combined report:

  * **Tab 1 — Summary:** every test with its pass / self-healed / fail / skip
    counts and grand totals.
  * **Tab 2 — Test details:** one collapsible per test, each embedding that
    test's full step-by-step report (the same content as the standalone
    ``bubblegum-report.html``, screenshots included) inside an isolated iframe so
    each test's styling/scripts can't collide.

How it works across processes: each run upserts itself (keyed by ``suite_name``)
into a sibling ``*.json`` manifest and writes its full detail HTML into a sibling
``<name>.d/`` directory. The combined HTML is then rebuilt from every recorded
run, so it always shows all tests — not just the last one. Re-running a test
replaces its row and detail. Delete the ``*.json`` manifest and ``*.d/`` dir to
reset the suite.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from bubblegum.core.schemas import StepResult

_MANIFEST_VERSION = 3


def _count_statuses(results: Sequence[StepResult]) -> dict[str, int]:
    counts = {"passed": 0, "recovered": 0, "failed": 0, "skipped": 0, "dry_run": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def compute_run_summary(results: Sequence[StepResult], suite_name: str) -> dict:
    """Build one test's summary record from its StepResults."""
    counts = _count_statuses(results)
    duration_ms = sum(int(getattr(r, "duration_ms", 0) or 0) for r in results)
    status = "failed" if counts["failed"] > 0 else "passed"
    return {
        "name": suite_name or "bubblegum",
        "status": status,
        "total": len(results),
        "passed": counts["passed"],
        "recovered": counts["recovered"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "dry_run": counts["dry_run"],
        "duration_ms": duration_ms,
        "last_run": datetime.now(timezone.utc).isoformat(),
    }


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "test").strip()).strip("-")
    return (s or "test")[:120]


def _manifest_path(html_path: Path) -> Path:
    return html_path.with_suffix(".json")


def _detail_dir(html_path: Path) -> Path:
    return html_path.with_suffix(".d")


def _load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("runs"), list):
                return data
        except Exception:  # noqa: BLE001 — a corrupt manifest starts fresh, never breaks a run
            pass
    return {"version": _MANIFEST_VERSION, "runs": []}


def _upsert(runs: list[dict], record: dict) -> list[dict]:
    out = [r for r in runs if r.get("name") != record["name"]]
    out.append(record)
    out.sort(key=lambda r: str(r.get("name", "")).lower())
    return out


def write_summary(
    results: Sequence[StepResult],
    path: str | Path = "bubblegum-summary.html",
    *,
    suite_name: str = "bubblegum",
    title: str = "Bubblegum Suite Report",
) -> Path:
    """Upsert this run and (re)render the combined summary + per-test detail report."""
    html_path = Path(path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = _manifest_path(html_path)
    detail_dir = _detail_dir(html_path)

    record = compute_run_summary(results, suite_name)

    # Render this test's full detail report into the sidecar dir (best-effort —
    # a detail failure must not lose the summary). Persisted so a later process
    # can rebuild the combined report with every test's detail, not just its own.
    try:
        from bubblegum.reporting.html_report import write_html_report
        detail_dir.mkdir(parents=True, exist_ok=True)
        detail_name = f"{_slug(record['name'])}.html"
        write_html_report(results, detail_dir / detail_name, title=record["name"])
        record["detail_file"] = detail_name
    except Exception:  # noqa: BLE001
        record["detail_file"] = None

    manifest = _load_manifest(manifest_path)
    manifest["version"] = _MANIFEST_VERSION
    manifest["runs"] = _upsert(manifest["runs"], record)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    html_path.write_text(_render_combined(manifest, detail_dir, title), encoding="utf-8")
    return html_path.resolve()


# ---------------------------------------------------------------------------
# HTML rendering (self-contained, no external assets)
# ---------------------------------------------------------------------------

def _totals(runs: list[dict]) -> dict:
    return {
        "tests": len(runs),
        "tests_passed": sum(1 for r in runs if r.get("status") == "passed"),
        "tests_failed": sum(1 for r in runs if r.get("status") == "failed"),
        "steps": sum(int(r.get("total", 0)) for r in runs),
        "passed": sum(int(r.get("passed", 0)) for r in runs),
        "recovered": sum(int(r.get("recovered", 0)) for r in runs),
        "failed": sum(int(r.get("failed", 0)) for r in runs),
        "skipped": sum(int(r.get("skipped", 0)) for r in runs),
    }


def _fmt_duration(ms: int) -> str:
    s = ms / 1000.0
    return f"{s:.1f}s" if s < 60 else f"{int(s // 60)}m {int(s % 60)}s"


def _srcdoc_escape(doc: str) -> str:
    # For an <iframe srcdoc="..."> double-quoted attribute: escape & then ".
    return doc.replace("&", "&amp;").replace('"', "&quot;")


def _summary_rows(runs: list[dict]) -> str:
    rows = []
    for r in runs:
        status = r.get("status", "passed")
        cls = "failed" if status == "failed" else "passed"
        rows.append(
            "<tr class='{cls}'>"
            "<td class='name'>{name}</td>"
            "<td><span class='badge {cls}'>{badge}</span></td>"
            "<td class='num'>{total}</td><td class='num pass'>{passed}</td>"
            "<td class='num heal'>{recovered}</td><td class='num fail'>{failed}</td>"
            "<td class='num skip'>{skipped}</td><td class='num'>{dur}</td>"
            "<td class='ts'>{ts}</td></tr>".format(
                cls=cls, name=html.escape(str(r.get("name", ""))),
                badge="PASS" if cls == "passed" else "FAIL",
                total=int(r.get("total", 0)), passed=int(r.get("passed", 0)),
                recovered=int(r.get("recovered", 0)), failed=int(r.get("failed", 0)),
                skipped=int(r.get("skipped", 0)), dur=_fmt_duration(int(r.get("duration_ms", 0))),
                ts=html.escape(str(r.get("last_run", ""))[:19].replace("T", " ")),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='9' class='empty'>No test runs recorded yet.</td></tr>"


def _detail_sections(runs: list[dict], detail_dir: Path) -> str:
    sections = []
    for r in runs:
        name = html.escape(str(r.get("name", "")))
        status = r.get("status", "passed")
        cls = "failed" if status == "failed" else "passed"
        badge = "PASS" if cls == "passed" else "FAIL"
        counts = (f"{int(r.get('total', 0))} steps · {int(r.get('passed', 0))} passed · "
                  f"{int(r.get('recovered', 0))} healed · {int(r.get('failed', 0))} failed")
        detail_file = r.get("detail_file")
        body = "<p class='missing'>Detailed report unavailable for this test.</p>"
        if detail_file:
            fpath = detail_dir / detail_file
            try:
                doc = fpath.read_text(encoding="utf-8")
                body = (f"<iframe class='detail-frame' loading='lazy' "
                        f"srcdoc=\"{_srcdoc_escape(doc)}\"></iframe>")
            except Exception:  # noqa: BLE001
                pass
        sections.append(
            f"<details class='test {cls}'>"
            f"<summary><span class='badge {cls}'>{badge}</span>"
            f"<span class='tname'>{name}</span>"
            f"<span class='tcounts'>{html.escape(counts)}</span></summary>"
            f"<div class='detail-wrap'>{body}</div></details>"
        )
    return "\n".join(sections) or "<p class='empty'>No test runs recorded yet.</p>"


def _render_combined(manifest: dict, detail_dir: Path, title: str) -> str:
    runs = manifest.get("runs", [])
    t = _totals(runs)
    generated = str(manifest.get("generated_at", ""))[:19].replace("T", " ")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; padding: 24px; background: #f6f7f9; color: #1c2430; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #6b7280; font-size: 12px; margin-bottom: 16px; }}
  .tabs {{ display: flex; gap: 8px; border-bottom: 2px solid #e5e7eb; margin-bottom: 20px; }}
  .tab {{ padding: 8px 16px; cursor: pointer; border: none; background: none; font-size: 14px;
         font-weight: 600; color: #6b7280; border-bottom: 2px solid transparent; margin-bottom: -2px; }}
  .tab.active {{ color: #2563eb; border-bottom-color: #2563eb; }}
  .panel {{ display: none; }} .panel.active {{ display: block; }}
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
  td.ts {{ color: #6b7280; }} tr.failed td.name {{ color: #b91c1c; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }}
  .badge.passed {{ background: #dcfce7; color: #15803d; }}
  .badge.failed {{ background: #fee2e2; color: #b91c1c; }}
  details.test {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; margin-bottom: 10px; overflow: hidden; }}
  details.test > summary {{ cursor: pointer; padding: 12px 16px; display: flex; align-items: center; gap: 12px; list-style: none; }}
  details.test > summary::-webkit-details-marker {{ display: none; }}
  details.test > summary::before {{ content: "▸"; color: #9ca3af; font-size: 12px; }}
  details.test[open] > summary::before {{ content: "▾"; }}
  .tname {{ font-weight: 600; }} .tcounts {{ color: #6b7280; font-size: 12px; margin-left: auto; }}
  .detail-wrap {{ border-top: 1px solid #f0f1f3; }}
  .detail-frame {{ width: 100%; height: 80vh; border: 0; background: #fff; }}
  .missing, .empty {{ color: #9ca3af; padding: 16px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f1115; color: #e5e7eb; }}
    .card, table, details.test {{ background: #171a21; border-color: #2a2f3a; }}
    th {{ background: #12151b; }} td, th {{ border-color: #232833; }} .tabs {{ border-color: #2a2f3a; }}
  }}
</style></head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="sub">Generated {html.escape(generated)} · {t['tests']} test(s)</div>

  <div class="tabs">
    <button class="tab active" data-panel="summary">Summary</button>
    <button class="tab" data-panel="details">Test details</button>
  </div>

  <section class="panel active" id="panel-summary">
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
{_summary_rows(runs)}
      </tbody>
    </table>
  </section>

  <section class="panel" id="panel-details">
{_detail_sections(runs, detail_dir)}
  </section>

  <script>
    document.querySelectorAll('.tab').forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        document.querySelectorAll('.tab').forEach(function (b) {{ b.classList.remove('active'); }});
        document.querySelectorAll('.panel').forEach(function (p) {{ p.classList.remove('active'); }});
        btn.classList.add('active');
        document.getElementById('panel-' + btn.dataset.panel).classList.add('active');
      }});
    }});
  </script>
</body></html>"""
