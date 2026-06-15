"""
bubblegum/cli/bridge.py
=======================
The ``bubblegum bridge`` command — run the JSON-RPC bridge over stdio.

Owns only the process lifecycle (build the server, serve on stdin/stdout, tear
sessions down on exit). All protocol/dispatch logic lives in
``bubblegum.bridge``. This is the entry point a spawned ``@bubblegum-ai/node``
client launches as a child process.
"""

from __future__ import annotations

import asyncio
import logging

from bubblegum.bridge import build_server, serve_stdio

logger = logging.getLogger(__name__)


async def _serve() -> None:
    server, sessions = build_server()
    try:
        await serve_stdio(server)
    finally:
        await sessions.close_all()


def run_bridge() -> int:
    """Synchronous entry point for the ``bridge`` subcommand. Returns exit code."""
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:  # pragma: no cover - interactive interrupt
        return 0
    except Exception as exc:  # noqa: BLE001 — clean CLI error
        logger.debug("bridge exited with error", exc_info=True)
        print(f"bridge exited with error: {exc}")
        return 1
    return 0
