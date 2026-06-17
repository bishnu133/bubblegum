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
        # ``results`` is a method on BubblegumSession (and a property on some
        # fakes) — normalize to the list either way.
        results = session.results
        if callable(results):
            results = results()
        title = params.get("title") or "Bubblegum Test Report"
        suite_name = params.get("suite_name") or "bubblegum"

        written: dict[str, str] = {}
        try:
            if params.get("html"):
                from bubblegum.reporting.html_report import write_html_report
                written["html"] = str(write_html_report(results, params["html"], title=title))
            if params.get("json"):
                from bubblegum.reporting.json_report import write_json_report
                written["json"] = str(write_json_report(results, params["json"], title=title))
            if params.get("junit"):
                from bubblegum.reporting.junit_report import write_junit_report
                written["junit"] = str(write_junit_report(results, params["junit"], suite_name=suite_name))
            if params.get("allure"):
                from bubblegum.reporting.allure_report import write_allure_results
                written["allure"] = str(write_allure_results(results, params["allure"], suite_name=suite_name))
        except OSError as exc:
            raise p.BridgeError(p.ENGINE_ERROR, f"report.write failed: {exc}") from exc

        if not written:
            raise p.BridgeError(
                p.INVALID_PARAMS,
                "report.write: specify at least one of html / json / junit / allure",
            )
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
