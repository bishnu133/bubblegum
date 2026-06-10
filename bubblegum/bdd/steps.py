"""
bubblegum/bdd/steps.py
======================
Ready-made pytest-bdd step definitions for the Bubblegum BDD layer.

Import this module from your pytest-bdd test (or a conftest) to register
catch-all When / Then steps that route the entire step text through
`bubblegum.bdd.dispatcher.execute_step`. The dispatcher does all of the phrase
parsing, so a single binding per keyword covers the whole grammar:

    # test_login_bdd.py
    from pytest_bdd import scenarios, given
    from bubblegum.bdd.steps import *          # registers When + Then steps
    scenarios("login.feature")

    # You provide the Given (setup/navigation) — URLs are environment-specific:
    @given("I am on the login page")
    async def _open(bubblegum_web, sample_app):
        await bubblegum_web.goto(f"{sample_app}/login.html")

Only When and Then are registered as catch-alls — deliberately not Given — so
your project-specific Given steps never collide with a `.+` catch-all. (For a
fully self-contained feature you can still navigate with a When, e.g.
`When I go to "http://127.0.0.1:8000/login.html"`.)

The steps depend on a `bubblegum_web` fixture (provided by Bubblegum's pytest
plugin) that yields an async BubblegumSession, and on `pytest-asyncio` for async
step execution.

Requires the optional dependency: pip install "bubblegum-ai[bdd]"
"""

from __future__ import annotations

try:
    from pytest_bdd import parsers, then, when
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "bubblegum.bdd.steps requires pytest-bdd. "
        'Install the BDD extra: pip install "bubblegum-ai[bdd]".'
    ) from exc

from bubblegum.bdd.dispatcher import execute_step

__all__ = ["when_step", "then_step"]

# A single catch-all per keyword — the dispatcher matches the actual phrasing.
# Given is intentionally NOT registered so project setup steps don't collide.
_ANY = parsers.re(r"(?P<step_text>.+)")


@when(_ANY)
async def when_step(bubblegum_web, step_text):
    return await execute_step(bubblegum_web, step_text)


@then(_ANY)
async def then_step(bubblegum_web, step_text):
    return await execute_step(bubblegum_web, step_text)
