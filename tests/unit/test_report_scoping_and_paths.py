"""Reporting enhancements: per-case scoping, directory-aware paths, run-id
tokens, and a configurable/persisted summary title.

These back four capabilities used to put several named tests in one test file
and keep every report:

  1. ``scope="since_last"`` reports only the steps run since the previous
     ``report.write`` — one report + one summary row per test case.
  2. A directory-valued report path auto-names ``<suite>.<ext>`` so per-test
     reports never overwrite one another.
  3. ``{run_id}`` / ``{timestamp}`` tokens fan runs out into per-execution
     folders (shared across processes via ``BUBBLEGUM_RUN_ID``).
  4. The combined summary header is a dedicated, persisted ``summary_title`` —
     the last test to run no longer decides the heading.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.bridge import handlers as h
from bubblegum.bridge.handlers import build_server
from bubblegum.bridge.sessions import OpenSpec, OpenedSession
from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.summary_report import (
    DEFAULT_SUMMARY_TITLE,
    write_summary,
)


def _step(action: str, status: str = "passed") -> StepResult:
    return StepResult(
        status=status,
        action=action,
        target=ResolvedTarget(ref="role=button", confidence=0.9, resolver_name="accessibility_tree"),
        confidence=0.9,
        duration_ms=3,
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_run_tokens_expand_from_env(monkeypatch):
    monkeypatch.setattr(h, "_RUN_ID_CACHE", None)
    monkeypatch.setenv("BUBBLEGUM_RUN_ID", "run-XYZ")
    assert h._expand_run_tokens("reports/{run_id}/summary.html") == "reports/run-XYZ/summary.html"
    assert h._expand_run_tokens("reports/{timestamp}/x.html") == "reports/run-XYZ/x.html"


def test_run_id_is_cached_and_stable(monkeypatch):
    monkeypatch.setattr(h, "_RUN_ID_CACHE", None)
    monkeypatch.delenv("BUBBLEGUM_RUN_ID", raising=False)
    first = h._run_id()
    # A later env change must not move an already-resolved run id.
    monkeypatch.setenv("BUBBLEGUM_RUN_ID", "different")
    assert h._run_id() == first


def test_directory_path_autonames_by_base(tmp_path):
    d = tmp_path / "reports"
    d.mkdir()
    got = h._resolve_report_path(str(d), ext=".html", base="badge-streak")
    assert got == str(d / "badge-streak.html")


def test_trailing_separator_is_directory(tmp_path):
    got = h._resolve_report_path(str(tmp_path) + "/", ext=".xml", base="my suite")
    assert got.endswith("/my-suite.xml")


def test_extensionless_path_is_directory():
    got = h._resolve_report_path("reports/run1", ext=".html", base="summary")
    assert got.replace("\\", "/") == "reports/run1/summary.html"


def test_plain_file_path_passes_through_unchanged():
    assert h._resolve_report_path("reports/one.html", ext=".html", base="x") == "reports/one.html"


# ---------------------------------------------------------------------------
# Summary title precedence / persistence
# ---------------------------------------------------------------------------

def test_summary_title_defaults_to_generic(tmp_path):
    out = write_summary([_step("a")], tmp_path / "s.html", suite_name="one", title="Test One")
    assert DEFAULT_SUMMARY_TITLE in out.read_text(encoding="utf-8")
    assert "Test One" not in out.read_text(encoding="utf-8").split("<body")[0]  # not in <title>/<h1>


def test_summary_title_is_persisted_and_not_clobbered(tmp_path):
    path = tmp_path / "s.html"
    # First run configures the header.
    write_summary([_step("a")], path, suite_name="one", title="Test One",
                  summary_title="Web Automation Summary Report")
    # A later run with a different per-test title must NOT change the header.
    out = write_summary([_step("b")], path, suite_name="two", title="Test Two")
    text = out.read_text(encoding="utf-8")
    assert "Web Automation Summary Report" in text
    manifest = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert manifest["title"] == "Web Automation Summary Report"
    # Both tests still show up as rows.
    assert {r["name"] for r in manifest["runs"]} == {"one", "two"}


# ---------------------------------------------------------------------------
# Bridge scope="since_last" (per-case)
# ---------------------------------------------------------------------------

class _CursorSession:
    """Mirrors BubblegumSession's result cursor for per-case reporting."""

    def __init__(self) -> None:
        self._results: list[StepResult] = []
        self._report_cursor = 0

    async def act(self, instruction, **kwargs):
        r = _step(instruction)
        self._results.append(r)
        return r

    def results(self) -> list[StepResult]:
        return list(self._results)

    def results_since_report(self) -> list[StepResult]:
        return list(self._results[self._report_cursor:])

    def advance_report_cursor(self) -> None:
        self._report_cursor = len(self._results)


def _server():
    fake = _CursorSession()

    async def factory(spec: OpenSpec) -> OpenedSession:
        async def aclose():
            pass

        return OpenedSession(session=fake, aclose=aclose)

    server, sessions = build_server(factory=factory)
    return server, fake


async def _call(server, method, params, request_id=1):
    msg = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    raw = await server.handle_message(json.dumps(msg))
    return json.loads(raw) if raw is not None else None


@pytest.mark.asyncio
async def test_scope_since_last_reports_only_current_case(tmp_path):
    server, _ = _server()
    resp = await _call(server, "session.open", {"channel": "web"})
    sid = resp["result"]["session_id"]

    # Case 1: two steps.
    await _call(server, "act", {"session_id": sid, "instruction": "step 1a"})
    await _call(server, "act", {"session_id": sid, "instruction": "step 1b"})
    r1 = await _call(server, "report.write", {
        "session_id": sid, "summary": str(tmp_path / "sum.html"),
        "suite_name": "case-one", "scope": "since_last",
    })
    assert r1["result"]["steps"] == 2

    # Case 2: one step — must be reported alone, not cumulatively.
    await _call(server, "act", {"session_id": sid, "instruction": "step 2a"})
    r2 = await _call(server, "report.write", {
        "session_id": sid, "summary": str(tmp_path / "sum.html"),
        "suite_name": "case-two", "scope": "since_last",
    })
    assert r2["result"]["steps"] == 1

    manifest = json.loads((tmp_path / "sum.json").read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in manifest["runs"]}
    assert rows["case-one"]["total"] == 2
    assert rows["case-two"]["total"] == 1


@pytest.mark.asyncio
async def test_default_scope_reports_all_steps(tmp_path):
    server, _ = _server()
    resp = await _call(server, "session.open", {"channel": "web"})
    sid = resp["result"]["session_id"]
    await _call(server, "act", {"session_id": sid, "instruction": "a"})
    await _call(server, "act", {"session_id": sid, "instruction": "b"})
    r = await _call(server, "report.write", {
        "session_id": sid, "html": str(tmp_path / "r.html"), "suite_name": "all",
    })
    assert r["result"]["steps"] == 2


@pytest.mark.asyncio
async def test_directory_path_keeps_per_suite_reports(tmp_path):
    server, _ = _server()
    resp = await _call(server, "session.open", {"channel": "web"})
    sid = resp["result"]["session_id"]
    await _call(server, "act", {"session_id": sid, "instruction": "a"})
    # Point html at a directory; the file is auto-named from the suite.
    r = await _call(server, "report.write", {
        "session_id": sid, "html": str(tmp_path) + "/", "suite_name": "badge-limited",
    })
    written = r["result"]["written"]["html"]
    assert written.endswith("badge-limited.html")
    assert (tmp_path / "badge-limited.html").exists()
