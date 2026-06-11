"""
bubblegum/bdd/fixtures.py
=========================
Self-contained pytest fixtures for driving Bubblegum BDD scenarios.

pytest-bdd runs steps synchronously, while the BubblegumSession + Playwright are
async. These fixtures bridge the gap by owning a dedicated event loop and
creating the async Playwright page + session on it, so the synchronous step
bindings in `bubblegum.bdd.steps` can drive the session with
`loop.run_until_complete(...)`.

They are deliberately independent of pytest-playwright / pytest-asyncio (which
do not compose cleanly with pytest-bdd's synchronous step runner) — the browser
is launched and torn down on the BDD loop itself.

Import both fixtures into your test module or a conftest:

    from bubblegum.bdd.fixtures import bubblegum_web, bubblegum_bdd_loop  # noqa: F401

Requires the `web` extra (Playwright) and a browser:
    pip install "bubblegum-ai[web,bdd]" && python -m playwright install chromium
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def bubblegum_bdd_loop():
    """A dedicated event loop the BDD steps run async session calls on."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def bubblegum_web(bubblegum_bdd_loop):
    """A BubblegumSession backed by a headless Chromium page on the BDD loop.

    Set BUBBLEGUM_BDD_HEADED=1 to watch the run in a visible browser.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        pytest.skip(f"Playwright not installed: {exc}")

    from bubblegum.session import BubblegumSession

    loop = bubblegum_bdd_loop
    headed = _env_headed()
    state: dict = {}

    async def _setup():
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=not headed)
        page = await browser.new_page()
        state["pw"] = pw
        state["browser"] = browser
        return BubblegumSession.web(page)

    session = loop.run_until_complete(_setup())
    try:
        yield session
    finally:
        async def _teardown():
            await state["browser"].close()
            await state["pw"].stop()

        loop.run_until_complete(_teardown())


def _env_headed() -> bool:
    import os

    return os.environ.get("BUBBLEGUM_BDD_HEADED", "").lower() in {"1", "true", "yes"}
