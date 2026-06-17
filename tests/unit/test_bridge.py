"""
Unit coverage for the JSON-RPC bridge (``bubblegum.bridge``).

These drive :meth:`BridgeServer.handle_message` directly with a **fake session
factory**, so the protocol/dispatch/handler wiring is exercised end-to-end with
no browser, device, or subprocess. The default (real) factory that launches
Playwright/Appium is intentionally not exercised here — that belongs to the
env-gated real-environment suites.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.bridge import protocol as p
from bubblegum.bridge.handlers import build_server
from bubblegum.bridge.sessions import OpenSpec, OpenedSession
from bubblegum.core.schemas import ResolvedTarget, StepResult


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class _FakeSession:
    """Records calls and returns canned StepResults, mimicking BubblegumSession."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.closed = False
        self._results: list[StepResult] = []

    def _result(self, action: str, status: str = "passed") -> StepResult:
        return StepResult(
            status=status,
            action=action,
            target=ResolvedTarget(ref="role=button[name='Login']", confidence=0.93, resolver_name="accessibility_tree"),
            confidence=0.93,
            duration_ms=5,
        )

    async def act(self, instruction, **kwargs):
        self.calls.append(("act", (instruction,), kwargs))
        r = self._result(instruction)
        self._results.append(r)
        return r

    def results(self) -> list[StepResult]:
        # A method, mirroring the real BubblegumSession.results() — so the
        # report handler is exercised against the actual call shape.
        return list(self._results)

    async def verify(self, instruction, **kwargs):
        self.calls.append(("verify", (instruction,), kwargs))
        return self._result(instruction)

    async def extract(self, instruction, **kwargs):
        self.calls.append(("extract", (instruction,), kwargs))
        r = self._result(instruction)
        r.target.metadata["extracted_value"] = "hello"
        return r

    async def recover(self, *, failed_selector, intent, **kwargs):
        self.calls.append(("recover", (failed_selector, intent), kwargs))
        return self._result(intent, status="recovered")

    async def is_visible(self, target, **kwargs):
        self.calls.append(("is_visible", (target,), kwargs))
        return True

    async def explain(self, instruction, *, print_output=True, **kwargs):
        return f"explanation for {instruction}"

    def summary(self):
        return {"total": 1, "passed": 1, "failed": 0}


def _server_with_fake():
    fake = _FakeSession()

    async def factory(spec: OpenSpec) -> OpenedSession:
        async def aclose():
            fake.closed = True

        return OpenedSession(session=fake, aclose=aclose)

    server, sessions = build_server(factory=factory)
    return server, sessions, fake


async def _call(server, method, params=None, request_id=1):
    msg = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        msg["params"] = params
    raw = await server.handle_message(json.dumps(msg))
    return json.loads(raw) if raw is not None else None


async def _open(server, **params):
    resp = await _call(server, "session.open", params or {"channel": "web"})
    return resp["result"]["session_id"]


# --------------------------------------------------------------------------
# Handshake / negotiation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_handshake_reports_version_and_capabilities():
    server, _, _ = _server_with_fake()
    resp = await _call(server, "handshake")
    result = resp["result"]
    assert result["protocol_version"] == p.PROTOCOL_VERSION
    assert "act" in result["capabilities"]
    assert "channel.web" in result["capabilities"]
    assert result["engine_version"]  # non-empty


# --------------------------------------------------------------------------
# Session lifecycle + primitives
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_act_returns_serialized_step_result():
    server, _, fake = _server_with_fake()
    sid = await _open(server)
    resp = await _call(server, "act", {"session_id": sid, "instruction": "Click Login"})
    result = resp["result"]
    assert result["status"] == "passed"
    assert result["action"] == "Click Login"
    assert result["target"]["resolver_name"] == "accessibility_tree"
    assert fake.calls[0][0] == "act"


@pytest.mark.asyncio
async def test_options_are_forwarded_as_kwargs():
    server, _, fake = _server_with_fake()
    sid = await _open(server)
    await _call(
        server,
        "act",
        {"session_id": sid, "instruction": "Click Login", "options": {"timeout_ms": 2000, "selector": "#login"}},
    )
    _, _, kwargs = fake.calls[0]
    assert kwargs == {"timeout_ms": 2000, "selector": "#login"}


@pytest.mark.asyncio
async def test_recover_maps_named_params():
    server, _, fake = _server_with_fake()
    sid = await _open(server)
    resp = await _call(
        server,
        "recover",
        {"session_id": sid, "failed_selector": "#old", "intent": "Click Login"},
    )
    assert resp["result"]["status"] == "recovered"
    assert fake.calls[0] == ("recover", ("#old", "Click Login"), {})


@pytest.mark.asyncio
async def test_extract_and_probe_and_summary():
    server, _, _ = _server_with_fake()
    sid = await _open(server)
    ex = await _call(server, "extract", {"session_id": sid, "instruction": "Get banner"})
    assert ex["result"]["target"]["metadata"]["extracted_value"] == "hello"
    vis = await _call(server, "is_visible", {"session_id": sid, "target": "Welcome"})
    assert vis["result"] == {"value": True}
    summ = await _call(server, "summary", {"session_id": sid})
    assert summ["result"]["passed"] == 1


@pytest.mark.asyncio
async def test_report_write_emits_requested_formats(tmp_path):
    server, _, _ = _server_with_fake()
    sid = await _open(server)
    await _call(server, "act", {"session_id": sid, "instruction": "Click Login"})
    await _call(server, "act", {"session_id": sid, "instruction": "Click Logout"})

    html = tmp_path / "report.html"
    allure = tmp_path / "allure-results"
    resp = await _call(
        server,
        "report.write",
        {"session_id": sid, "html": str(html), "allure": str(allure), "title": "Run"},
    )
    result = resp["result"]
    assert result["steps"] == 2
    assert set(result["written"]) == {"html", "allure"}
    assert html.exists() and html.read_text(encoding="utf-8").strip()
    assert allure.is_dir() and list(allure.glob("*-result.json"))


@pytest.mark.asyncio
async def test_report_write_requires_a_format():
    server, _, _ = _server_with_fake()
    sid = await _open(server)
    resp = await _call(server, "report.write", {"session_id": sid})
    assert resp["error"]["code"] == p.INVALID_PARAMS


@pytest.mark.asyncio
async def test_report_write_capability_is_advertised():
    server, _, _ = _server_with_fake()
    resp = await _call(server, "handshake")
    assert "report.write" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_close_tears_down_session():
    server, _, fake = _server_with_fake()
    sid = await _open(server)
    resp = await _call(server, "session.close", {"session_id": sid})
    assert resp["result"] == {"closed": True}
    assert fake.closed is True
    # second op on the closed session is a clean error, not a crash
    err = await _call(server, "act", {"session_id": sid, "instruction": "x"})
    assert err["error"]["code"] == p.SESSION_NOT_FOUND


# --------------------------------------------------------------------------
# Error handling
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_method():
    server, _, _ = _server_with_fake()
    resp = await _call(server, "nope")
    assert resp["error"]["code"] == p.METHOD_NOT_FOUND


@pytest.mark.asyncio
async def test_missing_required_param():
    server, _, _ = _server_with_fake()
    sid = await _open(server)
    resp = await _call(server, "act", {"session_id": sid})
    assert resp["error"]["code"] == p.INVALID_PARAMS


@pytest.mark.asyncio
async def test_act_without_session():
    server, _, _ = _server_with_fake()
    resp = await _call(server, "act", {"session_id": "missing", "instruction": "x"})
    assert resp["error"]["code"] == p.SESSION_NOT_FOUND


@pytest.mark.asyncio
async def test_parse_error_returns_null_id_response():
    server, _, _ = _server_with_fake()
    raw = await server.handle_message("{not json")
    resp = json.loads(raw)
    assert resp["error"]["code"] == p.PARSE_ERROR
    assert resp["id"] is None


@pytest.mark.asyncio
async def test_bad_channel_is_invalid_params():
    server, _, _ = _server_with_fake()
    resp = await _call(server, "session.open", {"channel": "desktop"})
    assert resp["error"]["code"] == p.INVALID_PARAMS


@pytest.mark.asyncio
async def test_notification_gets_no_response():
    server, _, _ = _server_with_fake()
    # No "id" → notification → server writes nothing.
    raw = await server.handle_message(json.dumps({"jsonrpc": "2.0", "method": "handshake"}))
    assert raw is None


@pytest.mark.asyncio
async def test_blank_line_is_ignored():
    server, _, _ = _server_with_fake()
    assert await server.handle_message("   ") is None


# --------------------------------------------------------------------------
# Serve loop wiring (in-memory transport, no stdio)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_serve_loop_processes_lines_until_eof():
    server, _, _ = _server_with_fake()
    inbox = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "handshake"}),
        "",  # blank line → no response
        None,  # EOF
    ]
    outbox: list[str] = []

    async def read_line():
        return inbox.pop(0)

    async def write_line(line):
        outbox.append(line)

    await server.serve(read_line, write_line)
    assert len(outbox) == 1
    assert json.loads(outbox[0])["result"]["protocol_version"] == p.PROTOCOL_VERSION
