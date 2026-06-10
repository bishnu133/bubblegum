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


# ---------------------------------------------------------------------------
# Probe fallback for content-named roles (the dashboard / settings probes)
#
# paragraph / status expose their text as snapshot content, not as an
# accessible name, so get_by_role(role, name=...) matches zero elements.
# The probe must fall back to an exact text locator in that case.
# ---------------------------------------------------------------------------


class _ProbeLocator:
    def __init__(self, count: int, visible: bool) -> None:
        self._count = count
        self._visible = visible

    @property
    def first(self) -> "_ProbeLocator":
        return self

    async def count(self) -> int:
        return self._count

    async def is_visible(self) -> bool:
        return self._visible


class _ProbePage:
    """Role locators match nothing; text locators match a visible element."""

    def __init__(self) -> None:
        self.url = "http://test/"
        self.get_by_text_calls: list[tuple[str, bool]] = []
        self.get_by_role_calls: list[str] = []

    def get_by_role(self, role: str, name: str | None = None) -> _ProbeLocator:
        self.get_by_role_calls.append(role)
        # paragraph/status have no accessible name -> zero matches; headings
        # take their name from content -> one match.
        count = 1 if role == "heading" else 0
        return _ProbeLocator(count=count, visible=count > 0)

    def get_by_text(self, text: str, exact: bool = False) -> _ProbeLocator:
        self.get_by_text_calls.append((text, exact))
        return _ProbeLocator(count=1, visible=True)

    def locator(self, ref: str) -> _ProbeLocator:
        return _ProbeLocator(count=0, visible=False)


def _probe_session_with_snapshot(snapshot: str):
    from unittest.mock import AsyncMock, MagicMock, patch

    from bubblegum.session import BubblegumSession

    page = _ProbePage()
    session = BubblegumSession.web(page)

    ctx = MagicMock()
    ctx.a11y_snapshot = snapshot
    ctx.screenshot = None
    ctx.screen_signature = "sig:probe"
    ctx.hierarchy_xml = None
    patcher = patch(
        "bubblegum.adapters.web.playwright.adapter.PlaywrightAdapter.collect_context",
        new=AsyncMock(return_value=ctx),
    )
    return page, session, patcher


def test_is_visible_falls_back_to_text_for_paragraph_role():
    import asyncio

    page, session, patcher = _probe_session_with_snapshot(
        '- heading "Dashboard" [level=1]\n- paragraph: Welcome back, tester.\n'
    )
    with patcher:
        visible = asyncio.run(session.is_visible("Welcome back, tester."))

    assert visible is True
    assert page.get_by_text_calls == [("Welcome back, tester.", True)]


def test_is_visible_falls_back_to_text_for_status_role():
    import asyncio

    page, session, patcher = _probe_session_with_snapshot(
        '- button "Save"\n- status: Settings saved.\n'
    )
    with patcher:
        visible = asyncio.run(session.is_visible("Settings saved."))

    assert visible is True
    assert page.get_by_text_calls == [("Settings saved.", True)]


def test_is_visible_keeps_role_locator_when_it_matches():
    import asyncio

    page, session, patcher = _probe_session_with_snapshot(
        '- heading "Dashboard" [level=1]\n- paragraph: Welcome back, tester.\n'
    )
    with patcher:
        visible = asyncio.run(session.is_visible("Dashboard"))

    assert visible is True
    # The heading locator matched, so no text fallback was needed.
    assert page.get_by_text_calls == []
