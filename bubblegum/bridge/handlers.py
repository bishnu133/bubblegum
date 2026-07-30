"""
bubblegum/bridge/handlers.py
============================
The bridge method set — a thin adapter from JSON-RPC params to the engine.

Each handler unpacks ``params``, calls the *existing* SDK/session surface, and
returns a JSON-serializable result. There is **no grounding logic here**: the
bridge deliberately re-uses ``bubblegum.core.sdk`` / ``BubblegumSession`` so the
Node client and the Python SDK share one engine and one ``StepResult`` shape.

:func:`build_server` wires a fresh :class:`SessionManager` + :class:`BridgeServer`
and returns both, so the CLI runner can tear sessions down on shutdown.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bubblegum import __version__
from bubblegum.bridge import protocol as p
from bubblegum.bridge.server import BridgeServer
from bubblegum.bridge.sessions import OpenSpec, SessionFactory, SessionManager


def _dump(result: Any) -> Any:
    """Serialize a StepResult (or any pydantic model) to a JSON-safe dict."""
    dump = getattr(result, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return result


# ---------------------------------------------------------------------------
# Report path helpers (run-id tokens + directory-aware naming)
# ---------------------------------------------------------------------------

def _run_id() -> str:
    """A stable id for this test *execution*.

    Prefer ``BUBBLEGUM_RUN_ID`` so every test file/process in one CI run shares
    a single value (and lands in the same timestamped folder); otherwise fall
    back to a per-process timestamp. Cached so repeated calls agree.
    """
    global _RUN_ID_CACHE
    if _RUN_ID_CACHE is None:
        _RUN_ID_CACHE = (
            os.environ.get("BUBBLEGUM_RUN_ID")
            or datetime.now().strftime("%Y%m%d-%H%M%S")
        )
    return _RUN_ID_CACHE


_RUN_ID_CACHE: str | None = None


def _expand_run_tokens(path: str) -> str:
    """Replace ``{run_id}`` / ``{timestamp}`` in a report path with the run id.

    Lets a tester write ``reports/{run_id}/summary.html`` and get one folder per
    execution — ideal CI artifacts, and older runs are never overwritten.
    """
    rid = _run_id()
    return path.replace("{run_id}", rid).replace("{timestamp}", rid)


def _report_slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "test").strip()).strip("-")
    return (s or "test")[:120]


def _resolve_report_path(raw: str, *, ext: str, base: str) -> str:
    """Resolve a report path, expanding run tokens and directory-valued paths.

    If ``raw`` names a directory (it exists as one, or ends with a path
    separator), the file is auto-named ``<base><ext>`` inside it — so per-test
    reports keyed by a distinct ``base`` (e.g. the suite name) never overwrite
    one another. A plain file path is returned unchanged (tokens aside).
    """
    expanded = _expand_run_tokens(raw)
    # Directory-valued when it ends with a separator, already exists as a
    # directory, or its final component carries no file extension.
    looks_like_dir = (
        expanded.endswith(("/", os.sep))
        or Path(expanded).is_dir()
        or not Path(expanded).suffix
    )
    if looks_like_dir:
        return str(Path(expanded) / f"{_report_slug(base)}{ext}")
    return expanded


def _require(params: dict[str, Any], key: str) -> Any:
    if key not in params or params[key] in (None, ""):
        raise p.BridgeError(p.INVALID_PARAMS, f"missing required param: {key!r}")
    return params[key]


class BridgeHandlers:
    """Holds the session registry and exposes one coroutine per RPC method."""

    def __init__(self, sessions: SessionManager) -> None:
        self.sessions = sessions

    # -- negotiation -----------------------------------------------------
    async def handshake(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "engine_version": __version__,
            "protocol_version": p.PROTOCOL_VERSION,
            "capabilities": list(p.CAPABILITIES),
        }

    # -- session lifecycle ----------------------------------------------
    async def session_open(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = await self.sessions.open(OpenSpec.from_params(params))
        return {"session_id": session_id}

    async def session_close(self, params: dict[str, Any]) -> dict[str, Any]:
        await self.sessions.close(params.get("session_id"))
        return {"closed": True}

    # -- the four primitives --------------------------------------------
    async def act(self, params: dict[str, Any]) -> Any:
        session = self.sessions.get(params.get("session_id"))
        instruction = _require(params, "instruction")
        return _dump(await session.act(instruction, **_options(params)))

    async def verify(self, params: dict[str, Any]) -> Any:
        session = self.sessions.get(params.get("session_id"))
        instruction = _require(params, "instruction")
        return _dump(await session.verify(instruction, **_options(params)))

    async def extract(self, params: dict[str, Any]) -> Any:
        session = self.sessions.get(params.get("session_id"))
        instruction = _require(params, "instruction")
        return _dump(await session.extract(instruction, **_options(params)))

    async def recover(self, params: dict[str, Any]) -> Any:
        session = self.sessions.get(params.get("session_id"))
        return _dump(
            await session.recover(
                failed_selector=_require(params, "failed_selector"),
                intent=_require(params, "intent"),
                **_options(params),
            )
        )

    # -- introspection / probes -----------------------------------------
    async def explain(self, params: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(params.get("session_id"))
        report = await session.explain(_require(params, "instruction"), print_output=False)
        return {"explanation": report}

    async def is_visible(self, params: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(params.get("session_id"))
        return {"value": await session.is_visible(_require(params, "target"))}

    async def is_checked(self, params: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(params.get("session_id"))
        return {"value": await session.is_checked(_require(params, "target"))}

    async def selected_value(self, params: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(params.get("session_id"))
        return {"value": await session.selected_value(_require(params, "target"))}

    async def summary(self, params: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.get(params.get("session_id"))
        return session.summary()

    # -- reporting -------------------------------------------------------
    async def report_write(self, params: dict[str, Any]) -> dict[str, Any]:
        """Write reports from the session's accumulated StepResults.

        Reuses the same writers as the pytest plugin, so a Node-driven run gets
        identical Allure/HTML/JSON/JUnit output. Each format key is optional and
        carries an output path (an ``allure`` directory). Reporting modules are
        imported lazily so the bridge stays cheap to start when no report is
        requested.
        """
        session = self.sessions.get(params.get("session_id"))
        title = params.get("title") or "Bubblegum Test Report"
        suite_name = params.get("suite_name") or "bubblegum"
        summary_title = params.get("summary_title")

        # ``scope="since_last"`` reports only the steps run since the previous
        # report.write — the primitive that lets several named test cases share
        # one session/test-file, each getting its own report + summary row. The
        # default ("all") is unchanged: report every step in the session.
        scope = params.get("scope") or "all"
        if scope == "since_last" and callable(getattr(session, "results_since_report", None)):
            results = session.results_since_report()
        else:
            # ``results`` is a method on BubblegumSession (and a property on some
            # fakes) — normalize to the list either way.
            results = session.results
            if callable(results):
                results = results()

        # Directory-valued paths auto-name ``<suite>.<ext>`` so per-test reports
        # never overwrite; ``{run_id}`` tokens fan runs out into per-execution
        # folders. Individual reports key on the suite name; the shared summary
        # keeps its own base name.
        def _ind(raw: str, ext: str) -> str:
            return _resolve_report_path(raw, ext=ext, base=suite_name)

        written: dict[str, str] = {}
        try:
            if params.get("html"):
                from bubblegum.reporting.html_report import write_html_report
                written["html"] = str(write_html_report(results, _ind(params["html"], ".html"), title=title))
            if params.get("json"):
                from bubblegum.reporting.json_report import write_json_report
                written["json"] = str(write_json_report(results, _ind(params["json"], ".json"), title=title))
            if params.get("junit"):
                from bubblegum.reporting.junit_report import write_junit_report
                written["junit"] = str(write_junit_report(results, _ind(params["junit"], ".xml"), suite_name=suite_name))
            if params.get("allure"):
                from bubblegum.reporting.allure_report import write_allure_results
                written["allure"] = str(write_allure_results(results, _expand_run_tokens(params["allure"]), suite_name=suite_name))
            if params.get("summary"):
                # Cross-run suite summary: upserts this run (keyed by suite_name)
                # into a manifest and renders an aggregated overview, so several
                # independently-run tests show one page instead of overwriting.
                from bubblegum.reporting.summary_report import write_summary
                summary_path = _resolve_report_path(params["summary"], ext=".html", base="summary")
                written["summary"] = str(
                    write_summary(
                        results, summary_path, suite_name=suite_name,
                        title=title, summary_title=summary_title,
                    )
                )
        except OSError as exc:
            raise p.BridgeError(p.ENGINE_ERROR, f"report.write failed: {exc}") from exc

        if not written:
            raise p.BridgeError(
                p.INVALID_PARAMS,
                "report.write: specify at least one of html / json / junit / allure / summary",
            )

        # Advance the cursor only after a successful per-case write, so the next
        # case's report starts from a clean slate.
        if scope == "since_last" and callable(getattr(session, "advance_report_cursor", None)):
            session.advance_report_cursor()

        return {"written": written, "steps": len(results)}

    # -- runtime config --------------------------------------------------
    async def configure_runtime(self, params: dict[str, Any]) -> dict[str, Any]:
        from bubblegum import configure_runtime as _configure

        _configure(config_path=params.get("config_path"))
        return {"ok": True}

    # -- wiring ----------------------------------------------------------
    def register_into(self, server: BridgeServer) -> None:
        server.register("handshake", self.handshake)
        server.register("session.open", self.session_open)
        server.register("session.close", self.session_close)
        server.register("act", self.act)
        server.register("verify", self.verify)
        server.register("extract", self.extract)
        server.register("recover", self.recover)
        server.register("explain", self.explain)
        server.register("is_visible", self.is_visible)
        server.register("is_checked", self.is_checked)
        server.register("selected_value", self.selected_value)
        server.register("summary", self.summary)
        server.register("report.write", self.report_write)
        server.register("configure_runtime", self.configure_runtime)


def _options(params: dict[str, Any]) -> dict[str, Any]:
    """Per-call options forwarded to the SDK as kwargs (e.g. timeout_ms, selector)."""
    opts = params.get("options") or {}
    if not isinstance(opts, dict):
        raise p.BridgeError(p.INVALID_PARAMS, "options must be an object")
    return dict(opts)


def build_server(factory: SessionFactory | None = None) -> tuple[BridgeServer, SessionManager]:
    """Construct a ready-to-serve bridge. Returns ``(server, session_manager)``."""
    sessions = SessionManager(factory=factory)
    handlers = BridgeHandlers(sessions)
    server = BridgeServer()
    handlers.register_into(server)
    return server, sessions
