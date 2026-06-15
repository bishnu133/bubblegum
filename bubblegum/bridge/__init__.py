"""
bubblegum.bridge — expose the engine over JSON-RPC for non-Python clients.

This is the server side of the dual-distribution plan in
``docs/distribution-npm-and-pypi.md``: the Python package stays the single source
of truth for grounding, and a thin client (e.g. the planned ``@bubblegum-ai/node``
npm package) drives the same four primitives over a small, version-negotiated
protocol. Run it with ``bubblegum bridge`` (stdio) or ``python -m bubblegum.bridge``.
"""

from bubblegum.bridge.protocol import CAPABILITIES, PROTOCOL_VERSION, BridgeError
from bubblegum.bridge.handlers import BridgeHandlers, build_server
from bubblegum.bridge.server import BridgeServer, serve_stdio
from bubblegum.bridge.sessions import OpenSpec, OpenedSession, SessionManager

__all__ = [
    "PROTOCOL_VERSION",
    "CAPABILITIES",
    "BridgeError",
    "BridgeServer",
    "BridgeHandlers",
    "SessionManager",
    "OpenSpec",
    "OpenedSession",
    "build_server",
    "serve_stdio",
]
