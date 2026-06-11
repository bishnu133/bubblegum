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

# Maps the historical repo-relative page locations to the sample-page sets that
# now ship *inside* the package (bubblegum/testing/pages/<name>). This lets the
# quickstart fixtures work for `pip install bubblegum-ai` users with no repo
# checkout, while a checkout still resolves the same pages.
_PACKAGED_PAGE_SETS: dict[str, str] = {
    "examples/web/widgets/widget_lab/pages": "widget_lab",
    "examples/web/real_local/pages": "sample_app",
}


def packaged_pages_dir(name: str) -> Path | None:
    """Return the on-disk directory of a packaged sample-page set, or None.

    `name` is a subdirectory of ``bubblegum/testing/pages`` (e.g. "widget_lab"
    or "sample_app"). Returns None when the package is installed in a way that
    is not backed by a real filesystem directory (e.g. a zipimport), so callers
    can fall back to a repository checkout.
    """
    try:
        from importlib.resources import files

        candidate = Path(str(files("bubblegum.testing") / "pages" / name))
    except Exception:
        return None
    return candidate if candidate.is_dir() else None


def find_pages_dir(
    start: Path | None = None,
    rel: Path | str = Path("examples/web/widgets/widget_lab/pages"),
) -> Path:
    """Locate an example pages directory.

    Resolution order:
      1. A repository checkout — walking up from `start` (defaults to the
         current working directory) until an ancestor contains `rel`. This
         keeps a dev checkout serving its own (possibly edited) example pages.
      2. The page set shipped inside the package — so pip-installed users with
         no repository checkout still get the quickstart fixtures.

    Defaults to the widget lab pages; pass ``rel`` to locate other example apps
    (e.g. the ``examples/web/real_local/pages`` sample app). Raises
    FileNotFoundError when neither source resolves.
    """
    rel = Path(rel)
    rel_key = rel.as_posix()

    base = (start or Path.cwd()).resolve()
    for candidate_root in [base, *base.parents]:
        candidate = candidate_root / rel
        if candidate.is_dir():
            return candidate

    # No repository checkout found — fall back to the page set bundled in the
    # installed package (pip install bubblegum-ai).
    packaged_name = _PACKAGED_PAGE_SETS.get(rel_key)
    if packaged_name is not None:
        packaged = packaged_pages_dir(packaged_name)
        if packaged is not None:
            return packaged

    raise FileNotFoundError(
        f"Could not locate {rel} at/above {base} or inside the bubblegum package. "
        "Install bubblegum-ai (the sample pages ship with the package) or run "
        "from a Bubblegum repository checkout."
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
