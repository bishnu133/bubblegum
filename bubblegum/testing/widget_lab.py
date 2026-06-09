"""Static HTTP server for the Bubblegum widget lab pages.

Shared by:
  - examples/web/widgets/widget_lab/run_example.py (CLI runner)
  - bubblegum.pytest_plugin.widget_lab fixture

Keeping a single implementation means the fixture and the script bind to
identical port-selection and shutdown semantics.
"""

from __future__ import annotations

import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_pages_dir(start: Path | None = None) -> Path:
    """Locate examples/web/widgets/widget_lab/pages by walking up from `start`.

    Defaults to the current working directory. Raises FileNotFoundError
    when no ancestor contains the expected layout — used by the fixture
    to fail fast with a clear message instead of serving an empty dir.
    """
    base = (start or Path.cwd()).resolve()
    rel = Path("examples/web/widgets/widget_lab/pages")
    for candidate_root in [base, *base.parents]:
        candidate = candidate_root / rel
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"Could not locate {rel} at or above {base}. "
        "The widget_lab fixture expects a Bubblegum repository checkout."
    )


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_widget_lab_server(
    pages_dir: Path | None = None,
) -> tuple[ThreadingHTTPServer, str]:
    """Start a daemon-threaded HTTP server serving widget lab pages.

    Returns (server, base_url). Call ``server.shutdown()`` to stop.
    """
    resolved = pages_dir if pages_dir is not None else find_pages_dir()
    port = _find_free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(resolved))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"
