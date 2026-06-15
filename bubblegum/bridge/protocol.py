"""
bubblegum/bridge/protocol.py
============================
Wire protocol for the Bubblegum bridge (``0.1.0`` slice).

The bridge exposes the Python engine over **JSON-RPC 2.0** so non-Python clients
(notably the planned ``@bubblegum-ai/node`` npm client) can drive the same four
primitives without re-implementing the grounding engine. See
``docs/distribution-npm-and-pypi.md``.

This module owns the version-negotiated contract and pure request/response
framing helpers only — no I/O, no engine calls — so it is trivially unit-testable
and safe to import anywhere.

Versioning
----------
``PROTOCOL_VERSION`` is an integer bumped **additively**: new methods / optional
fields raise it, but every previously shipped method keeps working. A client and
engine negotiate via :meth:`handshake`; an engine advertises every capability it
supports so a newer engine keeps serving an older client. This is the mechanism
that lets future enhancements ship at higher versions without breaking adopters.
"""

from __future__ import annotations

import json
from typing import Any

# Bumped additively. v1 = handshake + session lifecycle + the four primitives
# (act/verify/extract/recover) + state probes + summary + configure_runtime.
PROTOCOL_VERSION = 1

# Capability flags advertised by ``handshake``. Clients should feature-detect on
# these rather than on ``PROTOCOL_VERSION`` directly, so an engine can grow new
# capabilities within a protocol version line.
CAPABILITIES: tuple[str, ...] = (
    "session.open",
    "session.close",
    "act",
    "verify",
    "extract",
    "recover",
    "explain",
    "state_probes",   # is_visible / is_checked / selected_value
    "summary",
    "configure_runtime",
    "channel.web",
    "channel.mobile",
    "channel.web.cdp",   # attach to a client-owned Chromium over CDP (session.open cdp_endpoint)
)

# --- JSON-RPC 2.0 error codes -------------------------------------------------
# Standard codes (https://www.jsonrpc.org/specification#error_object):
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Bridge application codes live in the reserved server range (-32000..-32099):
SESSION_NOT_FOUND = -32001
ENGINE_ERROR = -32002
UNSUPPORTED = -32003


class BridgeError(Exception):
    """A handler-raised error carrying a JSON-RPC error ``code`` (+ optional data).

    Handlers raise this for *expected* failures (bad params, unknown session,
    engine error) so the server can turn them into a well-formed JSON-RPC error
    response instead of an opaque internal error.
    """

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class Request:
    """A parsed JSON-RPC request.

    ``id is None`` denotes a notification (the server sends no response). Parsing
    is intentionally lenient about ``params`` (object → kwargs-style dict, absent
    → empty dict) since every bridge method takes a params object.
    """

    __slots__ = ("id", "method", "params", "is_notification")

    def __init__(self, *, id: Any, method: str, params: dict[str, Any]) -> None:
        self.id = id
        self.method = method
        self.params = params
        self.is_notification = id is None

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> "Request":
        if not isinstance(payload, dict):
            raise BridgeError(INVALID_REQUEST, "request must be a JSON object")
        if payload.get("jsonrpc") != "2.0":
            raise BridgeError(INVALID_REQUEST, "jsonrpc must be '2.0'")
        method = payload.get("method")
        if not isinstance(method, str) or not method:
            raise BridgeError(INVALID_REQUEST, "method must be a non-empty string")
        params = payload.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            # We only support by-name params (an object); positional arrays are
            # rejected with a clear message rather than silently mishandled.
            raise BridgeError(INVALID_PARAMS, "params must be an object")
        return cls(id=payload.get("id"), method=method, params=params)


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def dumps(obj: Any) -> str:
    """Serialize a single message to a compact, newline-free JSON line."""
    return json.dumps(obj, separators=(",", ":"), default=str)
