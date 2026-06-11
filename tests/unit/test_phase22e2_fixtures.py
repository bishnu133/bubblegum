"""Phase 22E-2: pytest fixtures + bubblegum marker.

Covers:
  - `bubblegum` marker is registered (no warning, available in ini config)
  - `widget_lab` fixture is exposed by the plugin
  - `bubblegum_web` fixture is exposed when pytest-asyncio is available
  - `start_widget_lab_server` actually serves widget_lab page HTML
  - `find_pages_dir` walks up from a nested cwd to find the pages dir
  - `--bubblegum-headed` CLI option is registered

These tests stay clear of Playwright on purpose; the bubblegum_web fixture
itself is exercised against a real Chromium in
tests/playwright/test_phase22e2_widget_lab_fixtures.py (gated by
--playwright).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

import bubblegum.pytest_plugin as plugin
from bubblegum.testing.widget_lab import find_pages_dir, start_widget_lab_server


# ---------------------------------------------------------------------------
# Server helper
# ---------------------------------------------------------------------------


def test_start_widget_lab_server_serves_select_page():
    server, base_url = start_widget_lab_server()
    try:
        with urllib.request.urlopen(f"{base_url}/select.html", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
        # select.html is the native-select scenario page; ID #country is the
        # marker the lab scenarios drive against.
        assert 'id="country"' in body
    finally:
        server.shutdown()


def test_start_widget_lab_server_accepts_explicit_pages_dir(tmp_path: Path):
    page = tmp_path / "hello.html"
    page.write_text("<h1>hi</h1>")

    server, base_url = start_widget_lab_server(pages_dir=tmp_path)
    try:
        with urllib.request.urlopen(f"{base_url}/hello.html", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        assert "<h1>hi</h1>" in body
    finally:
        server.shutdown()


def test_find_pages_dir_walks_up_from_nested_subdir(tmp_path: Path, monkeypatch):
    # Build a fake repo layout so we exercise the walk-up logic without
    # depending on this repo's own checkout.
    pages = tmp_path / "examples" / "web" / "widgets" / "widget_lab" / "pages"
    pages.mkdir(parents=True)
    nested = tmp_path / "src" / "deep" / "nested"
    nested.mkdir(parents=True)

    found = find_pages_dir(nested)
    assert found.resolve() == pages.resolve()


def test_find_pages_dir_falls_back_to_packaged_when_no_checkout(tmp_path: Path):
    # No repo layout under tmp_path, but the widget_lab pages ship inside the
    # package, so resolution falls back to the bundled copy instead of raising.
    from bubblegum.testing.widget_lab import packaged_pages_dir

    found = find_pages_dir(tmp_path)
    assert found == packaged_pages_dir("widget_lab")
    assert (found / "modal.html").exists()


def test_find_pages_dir_raises_for_unknown_pageset(tmp_path: Path):
    # An unknown page set is neither in a checkout nor bundled — still raises.
    with pytest.raises(FileNotFoundError, match="does_not_exist"):
        find_pages_dir(tmp_path, rel="examples/web/widgets/does_not_exist/pages")


# ---------------------------------------------------------------------------
# Plugin surface
# ---------------------------------------------------------------------------


def test_widget_lab_fixture_is_exposed_by_plugin():
    assert hasattr(plugin, "widget_lab")
    # Session-scoped so the server lives across a whole pytest run. The
    # public attr name has churned across pytest versions; fall back to
    # the attribute name that holds the scope.
    fx = plugin.widget_lab
    scope = (
        getattr(getattr(fx, "_fixture_function_marker", None), "scope", None)
        or getattr(getattr(fx, "_pytestfixturefunction", None), "scope", None)
    )
    assert scope == "session", f"expected session-scoped fixture, got {scope!r}"


def test_bubblegum_web_fixture_is_exposed_when_pytest_asyncio_present():
    pytest.importorskip("pytest_asyncio")
    assert hasattr(plugin, "bubblegum_web")


def test_bubblegum_marker_is_registered(pytestconfig: pytest.Config):
    # pytest stores configured markers under `markers` in inivalues; each
    # entry starts with "<name>:" — the marker is registered when at least
    # one entry begins with "bubblegum:".
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("bubblegum:") for m in markers), markers


def test_bubblegum_headed_option_is_registered(pytestconfig: pytest.Config):
    # Reading getoption without a default returns the registered default
    # (False) — that confirms the option exists rather than raising
    # ValueError("no such option").
    assert pytestconfig.getoption("--bubblegum-headed") is False
