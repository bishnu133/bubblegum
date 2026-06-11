"""
PR5 — pytest-bdd wiring (no browser).

Validates that the `bubblegum.bdd.steps` bindings are actually discovered by
pytest-bdd and that the synchronous bindings really execute (and await) the
async session calls. Uses `pytester` to run an isolated sub-pytest with a fake
async session, so no Chromium is needed.

This guards two regressions that mocks alone would miss:
  - step discovery: `import *` must carry pytest-bdd's generated
    `pytestbdd_stepdef_*` fixtures (an over-narrow __all__ silently breaks it);
  - async execution: pytest-bdd does not await coroutine steps, so the bindings
    must drive the async session on an event loop themselves.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_bdd")

pytest_plugins = ["pytester"]


_FEATURE = """\
Feature: bdd wiring
  Scenario: actions execute and a true assertion holds
    Given the session is ready
    When I click "Sign in"
    And I enter "tester" into "Username"
    Then I should see "Dashboard"

  Scenario: a false assertion is actually evaluated
    Given the session is ready
    Then I should see "Missing"
"""

_TEST = """\
import asyncio
import pytest
from pytest_bdd import scenarios, given
from bubblegum.bdd.steps import *  # noqa: F401,F403  (brings generated step fixtures)
from bubblegum.core.schemas import StepResult

scenarios("wiring.feature")

class FakeSession:
    def __init__(self):
        self.acts = []
    async def act(self, instruction, **k):
        self.acts.append(instruction)
        return StepResult(status="passed", action=instruction)
    async def is_visible(self, target, **k):
        return target == "Dashboard"

@pytest.fixture
def bubblegum_web():
    return FakeSession()

@pytest.fixture
def bubblegum_bdd_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@given("the session is ready")
def _ready():
    return None
"""


def test_bdd_steps_discovered_and_execute(pytester):
    pytester.makefile(".feature", wiring=_FEATURE)
    pytester.makepyfile(test_wiring=_TEST)
    result = pytester.runpytest("-p", "no:cacheprovider")
    # The first scenario passes (steps ran, true assertion held); the second
    # fails with BddStepError (the false assertion was actually evaluated).
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.fnmatch_lines(["*Expected to see \"Missing\"*"])


def test_step_definition_fixtures_are_exported():
    # The generated step-definition fixtures must live in the module namespace so
    # `from bubblegum.bdd.steps import *` collects them.
    import bubblegum.bdd.steps as steps

    generated = [name for name in vars(steps) if name.startswith("pytestbdd_stepdef")]
    assert any("when" in n for n in generated)
    assert any("then" in n for n in generated)
