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

# Header shown on the combined summary page when the tester configures none.
# Deliberately generic (web *and* mobile suites use this report) — override per
# run with the ``summary_title`` argument / the Node ``summaryTitle`` option.
DEFAULT_SUMMARY_TITLE = "Test Automation Summary Report"


def _count_statuses(results: Sequence[StepResult]) -> dict[str, int]:
    counts = {"passed": 0, "recovered": 0, "failed": 0, "skipped": 0, "dry_run": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def _count_fallbacks(results: Sequence[StepResult]) -> int:
    """Steps resolved via the tester-provided fallback selector (a safety net).

    Reported apart from ``recovered`` (self-heal) so a degraded locator strategy
    shows up as its own tech-debt signal instead of masquerading as healing.
    """
    n = 0
    for r in results:
        target = getattr(r, "target", None)
        if target is None:
            continue
        meta = getattr(target, "metadata", None) or {}
        if getattr(target, "resolver_name", None) == "fallback_selector" or meta.get("fallback_selector_used"):
            n += 1
    return n


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
        "fallback": _count_fallbacks(results),
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
    summary_title: str | None = None,
) -> Path:
    """Upsert this run and (re)render the combined summary + per-test detail report.

    The combined page header is the *summary* title, which is independent of any
    single test's title so the last test to run no longer decides the heading:

      * ``summary_title`` (this call) wins and is persisted into the manifest;
      * otherwise the title stored by an earlier run is reused (first-writer
        wins, stable across the suite);
      * otherwise :data:`DEFAULT_SUMMARY_TITLE`.

    ``title`` still names each test's embedded detail report, unchanged.
    """
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
    # Resolve the header once and remember it, so an explicit summary_title from
    # any run sets it and later runs don't overwrite it with a per-test title.
    header = summary_title or manifest.get("title") or DEFAULT_SUMMARY_TITLE
    manifest["title"] = header
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    html_path.write_text(_render_combined(manifest, detail_dir, header), encoding="utf-8")
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
        "fallback": sum(int(r.get("fallback", 0)) for r in runs),
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
            "<td class='num heal'>{recovered}</td><td class='num fb'>{fallback}</td>"
            "<td class='num fail'>{failed}</td>"
            "<td class='num skip'>{skipped}</td><td class='num'>{dur}</td>"
            "<td class='ts'>{ts}</td></tr>".format(
                cls=cls, name=html.escape(str(r.get("name", ""))),
                badge="PASS" if cls == "passed" else "FAIL",
                total=int(r.get("total", 0)), passed=int(r.get("passed", 0)),
                recovered=int(r.get("recovered", 0)), fallback=int(r.get("fallback", 0)),
                failed=int(r.get("failed", 0)),
                skipped=int(r.get("skipped", 0)), dur=_fmt_duration(int(r.get("duration_ms", 0))),
                ts=html.escape(str(r.get("last_run", ""))[:19].replace("T", " ")),
            )
        )
    return "\n".join(rows) or "<tr><td colspan='10' class='empty'>No test runs recorded yet.</td></tr>"


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


# Outcome palette — reused by the donut, per-test bars and legend.
_OUTCOMES = [
    ("passed", "Passed", "var(--pass)"),
    ("recovered", "Self-healed", "var(--heal)"),
    ("fallback", "Fallback", "var(--fb)"),
    ("failed", "Failed", "var(--fail)"),
    ("skipped", "Skipped", "var(--skip)"),
]


def _donut_svg(parts: list[tuple[str, int, str]], center_big: str, center_small: str, size: int = 190) -> str:
    """A self-contained donut using the stroke-dasharray technique (no JS/libs)."""
    import math

    r = 70.0
    c = 2 * math.pi * r
    cx = cy = size / 2.0
    total = sum(v for _, v, _ in parts) or 1
    segs = ['<circle cx="%s" cy="%s" r="%s" fill="none" stroke="var(--track)" stroke-width="24"/>' % (cx, cy, r)]
    offset = 0.0
    for label, val, color in parts:
        if val <= 0:
            continue
        length = (val / total) * c
        segs.append(
            '<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="24" '
            'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" stroke-linecap="butt" '
            'transform="rotate(-90 %s %s)"><title>%s: %d</title></circle>'
            % (cx, cy, r, color, length, c - length, -offset, cx, cy, html.escape(label), val)
        )
        offset += length
    text = (
        '<text x="%s" y="%s" text-anchor="middle" class="donut-big">%s</text>'
        '<text x="%s" y="%s" text-anchor="middle" class="donut-small">%s</text>'
        % (cx, cy - 2, html.escape(center_big), cx, cy + 20, html.escape(center_small))
    )
    return (
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" class="donut" role="img">%s%s</svg>'
        % (size, size, size, size, "".join(segs), text)
    )


def _legend_html(t: dict) -> str:
    items = []
    for key, label, color in _OUTCOMES:
        items.append(
            '<div class="lg"><span class="dot" style="background:%s"></span>'
            '<span class="lg-l">%s</span><span class="lg-v">%d</span></div>'
            % (color, label, int(t.get(key, 0)))
        )
    return "".join(items)


def _test_bars_html(runs: list[dict]) -> str:
    rows = []
    for r in sorted(runs, key=lambda r: (r.get("status") != "failed", str(r.get("name", "")).lower())):
        total = max(int(r.get("total", 0)), 1)
        segs = []
        for key, _label, color in _OUTCOMES:
            v = int(r.get(key, 0))
            if v > 0:
                segs.append(
                    '<span class="seg" style="width:%.2f%%;background:%s" title="%s: %d"></span>'
                    % (v / total * 100, color, _label, v)
                )
        name = html.escape(str(r.get("name", "")))
        pr = int(r.get("passed", 0)) / total * 100
        cls = "fail" if r.get("status") == "failed" else "ok"
        rows.append(
            '<div class="bar-row"><div class="bar-name %s" title="%s">%s</div>'
            '<div class="bar">%s</div><div class="bar-pct">%.0f%%</div></div>'
            % (cls, name, name, "".join(segs), pr)
        )
    return "\n".join(rows) or '<p class="empty">No test runs recorded yet.</p>'


_SUMMARY_CSS = """
  :root{ color-scheme: light dark;
    --bg:#eef1f5; --panel:#ffffff; --border:#e5e8ee; --text:#161b22; --muted:#5b6472;
    --track:#eceef3; --accent:#4f46e5; --accent2:#7c3aed;
    --pass:#16a34a; --heal:#d97706; --fb:#a21caf; --fail:#dc2626; --skip:#9aa3b2;
    --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05); }
  @media (prefers-color-scheme: dark){ :root{
    --bg:#0d0f14; --panel:#161a22; --border:#252b36; --text:#e6e9ef; --muted:#9aa3b2;
    --track:#222834; --accent:#818cf8; --accent2:#a78bfa;
    --shadow:0 1px 2px rgba(0,0,0,.4); } }
  *{ box-sizing:border-box; }
  body{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    margin:0; padding:0; background:var(--bg); color:var(--text); -webkit-font-smoothing:antialiased; }
  .wrap{ max-width:1200px; margin:0 auto; padding:28px 24px 48px; }
  header.hero{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px;
    flex-wrap:wrap; margin-bottom:22px; }
  .hero h1{ font-size:22px; font-weight:800; margin:0; letter-spacing:-.02em;
    background:linear-gradient(90deg,var(--accent),var(--accent2)); -webkit-background-clip:text;
    background-clip:text; -webkit-text-fill-color:transparent; }
  .hero .sub{ color:var(--muted); font-size:12.5px; margin-top:4px; }
  .health{ display:flex; align-items:center; gap:10px; background:var(--panel); border:1px solid var(--border);
    border-radius:12px; padding:10px 16px; box-shadow:var(--shadow); }
  .health .pct{ font-size:26px; font-weight:800; font-variant-numeric:tabular-nums; }
  .health .lbl{ font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
  .pill{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700; }
  .pill.ok{ background:color-mix(in srgb,var(--pass) 16%, transparent); color:var(--pass); }
  .pill.bad{ background:color-mix(in srgb,var(--fail) 16%, transparent); color:var(--fail); }
  .tabs{ display:flex; gap:4px; margin-bottom:20px; background:var(--panel); border:1px solid var(--border);
    border-radius:12px; padding:4px; width:fit-content; box-shadow:var(--shadow); }
  .tab{ padding:8px 18px; cursor:pointer; border:none; background:none; font-size:13.5px; font-weight:600;
    color:var(--muted); border-radius:9px; transition:.15s; }
  .tab.active{ color:#fff; background:linear-gradient(90deg,var(--accent),var(--accent2)); }
  .panel{ display:none; } .panel.active{ display:block; animation:fade .2s ease; }
  @keyframes fade{ from{ opacity:0; transform:translateY(4px);} to{ opacity:1; transform:none;} }
  .kpis{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:14px; margin-bottom:18px; }
  .kpi{ background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:14px 16px;
    box-shadow:var(--shadow); position:relative; overflow:hidden; }
  .kpi .k{ font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
  .kpi .v{ font-size:26px; font-weight:800; margin-top:4px; font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
  .kpi .s{ font-size:11.5px; color:var(--muted); margin-top:2px; }
  .kpi .rail{ position:absolute; left:0; top:0; bottom:0; width:4px; }
  .v.pass{ color:var(--pass); } .v.fail{ color:var(--fail); } .v.heal{ color:var(--heal); }
  .v.fb{ color:var(--fb); } .v.skip{ color:var(--skip); } .v.accent{ color:var(--accent); }
  .charts{ display:grid; grid-template-columns:minmax(260px,340px) 1fr; gap:16px; margin-bottom:18px; }
  @media (max-width:820px){ .charts{ grid-template-columns:1fr; } }
  .chart{ background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:18px 20px;
    box-shadow:var(--shadow); }
  .chart h3{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin:0 0 12px; }
  .donut-wrap{ display:flex; align-items:center; gap:18px; flex-wrap:wrap; }
  .donut{ flex:0 0 auto; }
  .donut-big{ font-size:30px; font-weight:800; fill:var(--text); }
  .donut-small{ font-size:11px; fill:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  .legend{ display:flex; flex-direction:column; gap:8px; min-width:150px; }
  .lg{ display:flex; align-items:center; gap:8px; font-size:13px; }
  .lg .dot{ width:10px; height:10px; border-radius:3px; flex:0 0 auto; }
  .lg-l{ color:var(--muted); } .lg-v{ margin-left:auto; font-weight:700; font-variant-numeric:tabular-nums; }
  .bars{ display:flex; flex-direction:column; gap:10px; }
  .bar-row{ display:grid; grid-template-columns:150px 1fr 42px; align-items:center; gap:12px; }
  .bar-name{ font-size:13px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .bar-name.fail{ color:var(--fail); }
  .bar{ height:14px; border-radius:7px; overflow:hidden; background:var(--track); display:flex; }
  .bar .seg{ height:100%; }
  .bar-pct{ font-size:12px; font-weight:700; text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; }
  .table-card{ background:var(--panel); border:1px solid var(--border); border-radius:16px; overflow:hidden;
    box-shadow:var(--shadow); }
  table{ width:100%; border-collapse:collapse; }
  th,td{ padding:11px 14px; text-align:left; border-bottom:1px solid var(--border); font-size:13px; }
  tbody tr:last-child td{ border-bottom:none; }
  tbody tr:hover{ background:color-mix(in srgb,var(--accent) 5%, transparent); }
  th{ font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); font-weight:700; }
  td.num,th.num{ text-align:right; font-variant-numeric:tabular-nums; }
  td.name{ font-weight:650; }
  td.pass{ color:var(--pass); } td.heal{ color:var(--heal); } td.fail{ color:var(--fail); }
  td.skip{ color:var(--skip); } td.fb{ color:var(--fb); font-weight:700; }
  td.ts{ color:var(--muted); } tr.failed td.name{ color:var(--fail); }
  .badge{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700; }
  .badge.passed{ background:color-mix(in srgb,var(--pass) 16%, transparent); color:var(--pass); }
  .badge.failed{ background:color-mix(in srgb,var(--fail) 16%, transparent); color:var(--fail); }
  details.test{ background:var(--panel); border:1px solid var(--border); border-radius:14px; margin-bottom:10px; overflow:hidden; box-shadow:var(--shadow); }
  details.test > summary{ cursor:pointer; padding:13px 16px; display:flex; align-items:center; gap:12px; list-style:none; }
  details.test > summary::-webkit-details-marker{ display:none; }
  details.test > summary::before{ content:"\\25B8"; color:var(--muted); font-size:12px; }
  details.test[open] > summary::before{ content:"\\25BE"; }
  .tname{ font-weight:650; } .tcounts{ color:var(--muted); font-size:12px; margin-left:auto; }
  .detail-wrap{ border-top:1px solid var(--border); }
  .detail-frame{ width:100%; height:80vh; border:0; background:var(--panel); }
  .missing,.empty{ color:var(--muted); padding:16px; }
"""

_SUMMARY_JS = """
  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById('panel-' + btn.dataset.panel).classList.add('active');
    });
  });
"""


def _render_combined(manifest: dict, detail_dir: Path, title: str) -> str:
    runs = manifest.get("runs", [])
    t = _totals(runs)
    generated = str(manifest.get("generated_at", ""))[:19].replace("T", " ")
    total_ms = sum(int(r.get("duration_ms", 0)) for r in runs)

    tests = t["tests"] or 0
    test_pass_rate = round((t["tests_passed"] / tests) * 100) if tests else 0
    steps = t["steps"] or 0
    step_pass_rate = round((t["passed"] / steps) * 100) if steps else 0
    overall_ok = t["tests_failed"] == 0 and tests > 0
    health_pill = ('<span class="pill ok">All passing</span>' if overall_ok
                   else f'<span class="pill bad">{t["tests_failed"]} failing</span>' if tests
                   else '<span class="pill bad">No runs</span>')

    donut_parts = [(label, int(t.get(key, 0)), color) for key, label, color in _OUTCOMES]
    donut = _donut_svg(donut_parts, f"{step_pass_rate}%", "steps passed")

    kpis = (
        f'<div class="kpi"><span class="rail" style="background:var(--accent)"></span>'
        f'<div class="k">Tests</div><div class="v accent">{t["tests_passed"]}<span style="font-size:16px;color:var(--muted)">/{tests}</span></div>'
        f'<div class="s">{test_pass_rate}% pass rate</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--fail)"></span>'
        f'<div class="k">Tests Failed</div><div class="v fail">{t["tests_failed"]}</div><div class="s">of {tests} tests</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--text)"></span>'
        f'<div class="k">Total Steps</div><div class="v">{steps}</div><div class="s">{t["passed"]} passed</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--heal)"></span>'
        f'<div class="k">Self-healed</div><div class="v heal">{t["recovered"]}</div><div class="s">auto-recovered</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--fb)"></span>'
        f'<div class="k">Fallback ⚠</div><div class="v fb">{t["fallback"]}</div><div class="s">selector safety net</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--fail)"></span>'
        f'<div class="k">Steps Failed</div><div class="v fail">{t["failed"]}</div><div class="s">{t["skipped"]} skipped</div></div>'
        f'<div class="kpi"><span class="rail" style="background:var(--accent2)"></span>'
        f'<div class="k">Duration</div><div class="v">{_fmt_duration(total_ms)}</div><div class="s">total run time</div></div>'
    )

    body = f"""<div class="wrap">
  <header class="hero">
    <div><h1>{html.escape(title)}</h1>
      <div class="sub">Generated {html.escape(generated)} &middot; {tests} test(s) &middot; {steps} steps</div></div>
    <div class="health"><div><div class="lbl">Test pass rate</div><div class="pct">{test_pass_rate}%</div></div>{health_pill}</div>
  </header>

  <div class="tabs">
    <button class="tab active" data-panel="summary">Summary</button>
    <button class="tab" data-panel="details">Test details</button>
  </div>

  <section class="panel active" id="panel-summary">
    <div class="kpis">{kpis}</div>
    <div class="charts">
      <div class="chart"><h3>Step outcomes</h3>
        <div class="donut-wrap">{donut}<div class="legend">{_legend_html(t)}</div></div></div>
      <div class="chart"><h3>Per-test breakdown</h3>
        <div class="bars">{_test_bars_html(runs)}</div></div>
    </div>
    <div class="table-card"><table>
      <thead><tr>
        <th>Test</th><th>Status</th><th class="num">Steps</th><th class="num">Passed</th>
        <th class="num">Healed</th><th class="num">Fallback ⚠</th><th class="num">Failed</th><th class="num">Skipped</th>
        <th class="num">Duration</th><th>Last Run</th>
      </tr></thead>
      <tbody>
{_summary_rows(runs)}
      </tbody>
    </table></div>
  </section>

  <section class="panel" id="panel-details">
{_detail_sections(runs, detail_dir)}
  </section>
</div>"""

    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{_SUMMARY_CSS}</style></head>\n<body>\n"
        f"{body}\n<script>{_SUMMARY_JS}</script>\n</body></html>"
    )
