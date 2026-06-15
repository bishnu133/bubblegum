"""
bubblegum/bridge/server.py
==========================
Transport-agnostic JSON-RPC dispatch loop for the Bubblegum bridge.

:class:`BridgeServer` holds a registry of ``method name -> async handler`` and
turns a single inbound JSON line into a single outbound JSON line
(:meth:`handle_message`) — the unit the tests drive directly, with no sockets or
subprocess. :meth:`serve` wires that to any line reader/writer; :func:`serve_stdio`
binds it to ``stdin``/``stdout`` for the spawned-subprocess deployment the Node
client uses.

Handlers are ``async (params: dict) -> Any``. They return a JSON-serializable
result or raise :class:`~bubblegum.bridge.protocol.BridgeError` for an expected
failure; anything else becomes a JSON-RPC internal error (never crashes the loop).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Awaitable, Callable

from bubblegum.bridge import protocol as p

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


class BridgeServer:
    """Registry + dispatch for JSON-RPC methods. One per process."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        """Bind ``method`` to an async ``handler``. Last registration wins."""
        self._handlers[method] = handler

    def method_names(self) -> list[str]:
        return sorted(self._handlers)

    async def handle_message(self, raw: str) -> str | None:
        """Process one inbound JSON line; return the response line, or ``None``.

        ``None`` means "write nothing" — used for blank lines and for
        notifications (requests with no ``id``). A malformed line still produces
        a JSON-RPC error response with a null id, per the spec.
        """
        raw = raw.strip()
        if not raw:
            return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return p.dumps(p.error_response(None, p.PARSE_ERROR, f"parse error: {exc}"))

        try:
            request = p.Request.parse(payload)
        except p.BridgeError as exc:
            request_id = payload.get("id") if isinstance(payload, dict) else None
            return p.dumps(p.error_response(request_id, exc.code, exc.message, exc.data))

        response = await self._dispatch(request)
        if request.is_notification:
            return None
        return p.dumps(response)

    async def _dispatch(self, request: p.Request) -> dict[str, Any]:
        handler = self._handlers.get(request.method)
        if handler is None:
            return p.error_response(
                request.id, p.METHOD_NOT_FOUND, f"method not found: {request.method}"
            )
        try:
            result = await handler(request.params)
            return p.success_response(request.id, result)
        except p.BridgeError as exc:
            return p.error_response(request.id, exc.code, exc.message, exc.data)
        except Exception as exc:  # noqa: BLE001 — never let one call kill the loop
            logger.exception("bridge handler %r failed", request.method)
            return p.error_response(
                request.id, p.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"
            )

    async def serve(
        self,
        read_line: Callable[[], Awaitable[str | None]],
        write_line: Callable[[str], Awaitable[None]],
    ) -> None:
        """Run the read→dispatch→write loop until ``read_line`` returns ``None``."""
        while True:
            line = await read_line()
            if line is None:
                return
            response = await self.handle_message(line)
            if response is not None:
                await write_line(response)


async def serve_stdio(server: BridgeServer) -> None:
    """Serve ``server`` over newline-delimited JSON on stdin/stdout.

    Each request is one line in; each response is one line out. stdin is read on
    a worker thread so the event loop stays free for engine work.
    """

    async def read_line() -> str | None:
        line = await asyncio.to_thread(sys.stdin.readline)
        if line == "":  # EOF
            return None
        return line

    def _write(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    async def write_line(line: str) -> None:
        await asyncio.to_thread(_write, line)

    await server.serve(read_line, write_line)
