"""Phase 22E-9: Acme Notes sample app + sample_app fixture.

Covers (no browser needed):
  - the three sample pages exist and carry the markers the quickstart
    instructions resolve against (labels, button text, link text)
  - find_pages_dir accepts a custom `rel` and still defaults to widget_lab
  - the static server serves the sample login page
  - the `sample_app` fixture is exposed by the plugin, session-scoped

The full login → dashboard → settings NL flow runs against real Chromium
in tests/integration/test_phase22e9_sample_app.py (gated by --playwright).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

import bubblegum.pytest_plugin as plugin
from bubblegum.testing.widget_lab import find_pages_dir, start_widget_lab_server

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PAGES = REPO_ROOT / "examples" / "web" / "real_local" / "pages"


# ---------------------------------------------------------------------------
# Page content — keep the quickstart's NL instructions resolvable
# ---------------------------------------------------------------------------


def test_sample_app_has_three_pages():
    names = sorted(p.name for p in SAMPLE_PAGES.glob("*.html"))
    assert names == ["dashboard.html", "login.html", "settings.html"]


def test_login_page_carries_quickstart_markers():
    html = (SAMPLE_PAGES / "login.html").read_text()
    # 'Enter "tester" into Username' / Password need labelled inputs;
    # "Click Sign in" needs the button text; the failure branch needs
    # the alert copy.
    assert '<label for="username">Username</label>' in html
    assert '<label for="password">Password</label>' in html
    assert ">Sign in</button>" in html
    assert "Invalid username or password." in html


def test_dashboard_page_carries_quickstart_markers():
    html = (SAMPLE_PAGES / "dashboard.html").read_text()
    assert "<h1>Dashboard</h1>" in html
    assert ">Settings</a>" in html  # "Click the Settings link"
    assert "Welcome back, tester." in html


def test_settings_page_carries_quickstart_markers():
    html = (SAMPLE_PAGES / "settings.html").read_text()
    assert '<label for="notify">Email notifications</label>' in html
    assert '<label for="language">Language</label>' in html
    assert ">German</option>" in html
    assert ">Save</button>" in html
    assert "Settings saved." in html


# ---------------------------------------------------------------------------
# find_pages_dir rel parameter
# ---------------------------------------------------------------------------


def test_find_pages_dir_default_still_widget_lab():
    found = find_pages_dir(REPO_ROOT)
    assert found == REPO_ROOT / "examples" / "web" / "widgets" / "widget_lab" / "pages"


def test_find_pages_dir_locates_sample_app_via_rel():
    found = find_pages_dir(REPO_ROOT, rel="examples/web/real_local/pages")
    assert found == SAMPLE_PAGES


def test_find_pages_dir_rel_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="real_local"):
        find_pages_dir(tmp_path, rel="examples/web/real_local/pages")


# ---------------------------------------------------------------------------
# Server + fixture surface
# ---------------------------------------------------------------------------


def test_server_serves_sample_login_page():
    server, base_url = start_widget_lab_server(pages_dir=SAMPLE_PAGES)
    try:
        with urllib.request.urlopen(f"{base_url}/login.html", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        assert "Acme Notes" in body
    finally:
        server.shutdown()


def test_sample_app_fixture_is_exposed_and_session_scoped():
    assert hasattr(plugin, "sample_app")
    fx = plugin.sample_app
    scope = (
        getattr(getattr(fx, "_fixture_function_marker", None), "scope", None)
        or getattr(getattr(fx, "_pytestfixturefunction", None), "scope", None)
    )
    assert scope == "session", f"expected session-scoped fixture, got {scope!r}"
