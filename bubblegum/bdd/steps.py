"""
bubblegum/bdd/steps.py
======================
Ready-made pytest-bdd step definitions for the Bubblegum BDD layer.

pytest-bdd executes steps synchronously and does NOT await coroutine step
functions, so these bindings are synchronous and drive the async
BubblegumSession on a dedicated event loop provided by the `bubblegum_bdd_loop`
fixture (see `bubblegum.bdd.fixtures`). The session's page must be created on
that same loop — the bundled `bubblegum_web` fixture in `bubblegum.bdd.fixtures`
does exactly that.

Usage:

    # test_login_bdd.py
    from pytest_bdd import scenarios, given
    from bubblegum.bdd.steps import *                 # When + Then steps
    from bubblegum.bdd.fixtures import bubblegum_web, bubblegum_bdd_loop  # noqa: F401

    scenarios("login.feature")

    @given("I am on the login page")
    def _open(bubblegum_web, bubblegum_bdd_loop, sample_app):
        bubblegum_bdd_loop.run_until_complete(
            bubblegum_web.goto(f"{sample_app}/login.html")
        )

Only When and Then are registered as catch-alls (the dispatcher parses the
actual phrasing); Given is left to the project so custom setup never collides.

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

# NOTE: no __all__ on purpose. pytest-bdd's @when/@then inject step-definition
# fixtures named `pytestbdd_stepdef_*` into this module's globals. Users register
# the steps with `from bubblegum.bdd.steps import *`, which must carry those
# generated fixtures across — an __all__ that omitted them would silently break
# step discovery (StepDefinitionNotFoundError).

# A single catch-all per keyword — the dispatcher matches the actual phrasing.
# Given is intentionally NOT registered so project setup steps don't collide.
_ANY = parsers.re(r"(?P<step_text>.+)")


def _drive(bubblegum_web, bubblegum_bdd_loop, step_text):
    return bubblegum_bdd_loop.run_until_complete(
        execute_step(bubblegum_web, step_text)
    )


@when(_ANY)
def when_step(bubblegum_web, bubblegum_bdd_loop, step_text):
    return _drive(bubblegum_web, bubblegum_bdd_loop, step_text)


@then(_ANY)
def then_step(bubblegum_web, bubblegum_bdd_loop, step_text):
    return _drive(bubblegum_web, bubblegum_bdd_loop, step_text)
