"""Phase 22E-7: BubblegumSession.goto + bubblegum_browser/bubblegum_page split.

Covers:
  - `goto()` navigates the wrapped page with the default domcontentloaded wait
  - `goto()` forwards a custom wait_until
  - `goto()` is web-only (mobile sessions raise NotImplementedError)
  - `bubblegum_browser` fixture is exposed and session-scoped
  - `bubblegum_page` fixture is exposed and function-scoped

The fixtures are exercised against real Chromium in
tests/integration/test_phase22e7_browser_fixtures.py (gated by --playwright).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import bubblegum.pytest_plugin as plugin
from bubblegum.session import BubblegumSession


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, dict[str, Any]]] = []

    async def goto(self, url: str, **kwargs: Any) -> None:
        self.goto_calls.append((url, kwargs))


def _fixture_scope(fx) -> str | None:
    # The attribute holding fixture metadata has churned across pytest /
    # pytest-asyncio versions; check the known spellings.
    return (
        getattr(getattr(fx, "_fixture_function_marker", None), "scope", None)
        or getattr(getattr(fx, "_pytestfixturefunction", None), "scope", None)
    )


# ---------------------------------------------------------------------------
# BubblegumSession.goto
# ---------------------------------------------------------------------------


def test_goto_navigates_with_domcontentloaded_default():
    page = _FakePage()
    session = BubblegumSession.web(page)

    asyncio.run(session.goto("http://lab.test/radios.html"))

    assert page.goto_calls == [
        ("http://lab.test/radios.html", {"wait_until": "domcontentloaded"})
    ]


def test_goto_forwards_custom_wait_until():
    page = _FakePage()
    session = BubblegumSession.web(page)

    asyncio.run(session.goto("http://lab.test/tabs.html", wait_until="load"))

    assert page.goto_calls == [("http://lab.test/tabs.html", {"wait_until": "load"})]


def test_goto_raises_for_mobile_session():
    session = BubblegumSession.mobile(driver=object())

    with pytest.raises(NotImplementedError, match="web sessions"):
        asyncio.run(session.goto("http://lab.test/"))


# ---------------------------------------------------------------------------
# Plugin surface
# ---------------------------------------------------------------------------


def test_bubblegum_browser_fixture_is_exposed_and_session_scoped():
    pytest.importorskip("pytest_asyncio")
    assert hasattr(plugin, "bubblegum_browser")
    assert _fixture_scope(plugin.bubblegum_browser) == "session"


def test_bubblegum_page_fixture_is_exposed_and_function_scoped():
    pytest.importorskip("pytest_asyncio")
    assert hasattr(plugin, "bubblegum_page")
    assert _fixture_scope(plugin.bubblegum_page) == "function"
