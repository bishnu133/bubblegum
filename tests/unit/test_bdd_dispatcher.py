"""
PR5 — BDD step dispatcher.

Tests the framework-agnostic Gherkin-step dispatcher with a fake async session,
so the phrase -> action mapping is covered without a browser or pytest-bdd.
"""

from __future__ import annotations

import pytest

from bubblegum.bdd import BddStepError, execute_step
from bubblegum.core.schemas import ErrorInfo, ResolvedTarget, StepResult


class FakeSession:
    """Records act/goto calls and answers probes from preset state."""

    def __init__(self):
        self.acts: list[str] = []
        self.gotos: list[str] = []
        self.visible: set[str] = set()
        self.checked: set[str] = set()
        self.values: dict[str, str] = {}
        self.texts: dict[str, str] = {}
        self.fail_instructions: set[str] = set()
        self.recovered_instructions: set[str] = set()

    async def goto(self, url, **_):
        self.gotos.append(url)

    async def act(self, instruction, **_):
        self.acts.append(instruction)
        if instruction in self.fail_instructions:
            return StepResult(
                status="failed",
                action=instruction,
                error=ErrorInfo(error_type="ResolutionFailedError", message="no match"),
            )
        status = "recovered" if instruction in self.recovered_instructions else "passed"
        return StepResult(status=status, action=instruction)

    async def is_visible(self, target, **_):
        return target in self.visible

    async def is_checked(self, target, **_):
        return target in self.checked

    async def selected_value(self, target, **_):
        return self.values.get(target, "")

    async def extract(self, instruction, **_):
        # instruction is "Get text of <target>"
        target = instruction.replace("Get text of ", "", 1)
        value = self.texts.get(target, "")
        return StepResult(
            status="passed",
            action=instruction,
            target=ResolvedTarget(
                ref="x", confidence=1.0, resolver_name="t",
                metadata={"extracted_value": value},
            ),
        )


@pytest.fixture
def session():
    return FakeSession()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    'I open "http://x/login.html"',
    'open the page "http://x/login.html"',
    'go to "http://x/login.html"',
    'I am on "http://x/login.html"',
])
async def test_navigation_variants(session, text):
    await execute_step(session, text)
    assert session.gotos == ["http://x/login.html"]


# ---------------------------------------------------------------------------
# Actions -> act() instruction reconstruction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_click(session):
    await execute_step(session, 'I click "Sign in"')
    assert session.acts == ["Click Sign in"]


@pytest.mark.asyncio
async def test_click_without_leading_i(session):
    await execute_step(session, 'click on "Sign in"')
    assert session.acts == ["Click Sign in"]


@pytest.mark.asyncio
async def test_enter_into(session):
    await execute_step(session, 'I enter "tester" into "Username"')
    assert session.acts == ['Enter "tester" into Username']


@pytest.mark.asyncio
async def test_fill_with(session):
    await execute_step(session, 'fill "Password" with "secret"')
    assert session.acts == ['Enter "secret" into Password']


@pytest.mark.asyncio
async def test_select_from(session):
    await execute_step(session, 'I select "German" from "Language"')
    assert session.acts == ["Select German from Language"]


@pytest.mark.asyncio
async def test_check_uncheck(session):
    await execute_step(session, 'check "Email notifications"')
    await execute_step(session, 'uncheck "Email notifications"')
    assert session.acts == ["Check Email notifications", "Uncheck Email notifications"]


@pytest.mark.asyncio
async def test_raw_passthrough(session):
    await execute_step(session, 'I run "Click the Settings link"')
    assert session.acts == ["Click the Settings link"]


# ---------------------------------------------------------------------------
# Action failure / recovery semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_action_raises(session):
    session.fail_instructions.add("Click Ghost")
    with pytest.raises(BddStepError, match="failed"):
        await execute_step(session, 'click "Ghost"')


@pytest.mark.asyncio
async def test_recovered_action_passes(session):
    session.recovered_instructions.add("Click Sign in")
    result = await execute_step(session, 'click "Sign in"')
    assert result.status == "recovered"  # healed step passes (advisory in report)


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_should_see_pass_and_fail(session):
    session.visible.add("Dashboard")
    await execute_step(session, 'I should see "Dashboard"')          # passes
    await execute_step(session, '"Dashboard" should be visible')     # passes
    with pytest.raises(BddStepError, match="not visible"):
        await execute_step(session, 'I should see "Missing"')


@pytest.mark.asyncio
async def test_should_not_see(session):
    await execute_step(session, 'I should not see "Error"')          # passes (absent)
    session.visible.add("Error")
    with pytest.raises(BddStepError):
        await execute_step(session, 'I should not see "Error"')


@pytest.mark.asyncio
async def test_checked_assertions(session):
    session.checked.add("Email notifications")
    await execute_step(session, '"Email notifications" should be checked')
    with pytest.raises(BddStepError):
        await execute_step(session, '"Marketing" should be checked')


@pytest.mark.asyncio
async def test_has_value(session):
    session.values["Language"] = "de"
    await execute_step(session, '"Language" should have value "de"')
    with pytest.raises(BddStepError, match="value"):
        await execute_step(session, '"Language" should have value "en"')


@pytest.mark.asyncio
async def test_contains(session):
    session.texts["Greeting"] = "Welcome back, tester."
    await execute_step(session, '"Greeting" should contain "Welcome back"')
    with pytest.raises(BddStepError, match="contain"):
        await execute_step(session, '"Greeting" should contain "Goodbye"')


# ---------------------------------------------------------------------------
# Unmatched step
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unmatched_step_raises_helpful_error(session):
    with pytest.raises(BddStepError, match="No Bubblegum BDD step matches"):
        await execute_step(session, "frobnicate the gizmo")


@pytest.mark.asyncio
async def test_trailing_period_and_case_insensitive(session):
    await execute_step(session, 'CLICK "Sign in".')
    assert session.acts == ["Click Sign in"]
