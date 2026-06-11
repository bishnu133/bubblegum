"""
bubblegum/bdd/dispatcher.py
===========================
Framework-agnostic Gherkin-step dispatcher for the Bubblegum BDD layer.

`execute_step(session, text)` maps a single Given/When/Then step's text (the
keyword already stripped by the BDD runner) onto a call on a BubblegumSession.
It is intentionally independent of pytest-bdd / behave so the phrase -> action
mapping can be unit-tested without a browser or a BDD runner, and reused by any
binding.

Supported phrasings (case-insensitive; an optional leading "I " is ignored, a
trailing period is stripped):

  Navigation
    open "<url>" | go to "<url>" | navigate to "<url>" | visit "<url>"
    am on "<url>"                         (Given I am on "...")

  Actions (translated into a natural-language instruction for session.act)
    click "<x>" | tap "<x>" | press "<x>"
    enter "<v>" into "<f>" | type "<v>" into "<f>"
    fill "<f>" with "<v>"
    select "<v>" from "<f>" | choose "<v>" from "<f>"
    check "<x>" | uncheck "<x>"
    run "<instruction>" | do "<instruction>"   (raw NL passthrough)

  Assertions
    should see "<x>" | should not see "<x>"
    "<x>" should be visible | "<x>" should not be visible
    "<x>" should be checked | "<x>" should not be checked
    "<f>" should have value "<v>"
    "<x>" should contain "<v>"

Action steps fail the scenario (raise BddStepError) when the underlying step
resolves to status "failed". A "recovered" (self-healed) step passes, so the
healing advisory surfaces in the report rather than blocking the run.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["BddStepError", "execute_step", "STEP_PATTERNS"]


class BddStepError(AssertionError):
    """Raised when a BDD step cannot be mapped or its action failed.

    Subclasses AssertionError so BDD runners report it as a test failure.
    """


def _normalize(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    # Drop a single leading "I " so "I click ..." and "click ..." both work.
    cleaned = re.sub(r"^I\s+", "", cleaned, count=1, flags=re.IGNORECASE)
    return cleaned


# Each entry: (compiled regex, handler name). Handlers are methods below.
def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


STEP_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Navigation
    (_c(r'^(?:open|go to|navigate to|visit)(?: the page)? "([^"]+)"$'), "goto"),
    (_c(r'^am on(?: the page)? "([^"]+)"$'), "goto"),
    # Actions
    (_c(r'^(?:click|tap|press)(?: on)? "([^"]+)"$'), "click"),
    (_c(r'^(?:enter|type|input) "([^"]*)" (?:in|into) "([^"]+)"$'), "enter"),
    (_c(r'^fill "([^"]+)" with "([^"]*)"$'), "fill"),
    (_c(r'^(?:select|choose) "([^"]+)" from "([^"]+)"$'), "select"),
    (_c(r'^check "([^"]+)"$'), "check"),
    (_c(r'^uncheck "([^"]+)"$'), "uncheck"),
    (_c(r'^(?:run|do|perform|act) "([^"]+)"$'), "raw"),
    # Assertions
    (_c(r'^should see "([^"]+)"$'), "see"),
    (_c(r'^should not see "([^"]+)"$'), "not_see"),
    (_c(r'^"([^"]+)" should be visible$'), "see"),
    (_c(r'^"([^"]+)" should not be visible$'), "not_see"),
    (_c(r'^"([^"]+)" should be checked$'), "checked"),
    (_c(r'^"([^"]+)" should not be checked$'), "not_checked"),
    (_c(r'^"([^"]+)" should have value "([^"]*)"$'), "has_value"),
    (_c(r'^"([^"]+)" should contain "([^"]+)"$'), "contains"),
]


async def execute_step(session: Any, text: str) -> Any:
    """Map a single Gherkin step's text onto a BubblegumSession call.

    Args:
        session: a BubblegumSession (or any object exposing the async methods
            act / goto / is_visible / is_checked / selected_value / extract).
        text: the step text with the Given/When/Then keyword already stripped.

    Returns:
        The StepResult for action steps; None for assertion steps.

    Raises:
        BddStepError: if no pattern matches, or an action step failed, or an
            assertion did not hold.
    """
    normalized = _normalize(text)
    for pattern, handler in STEP_PATTERNS:
        m = pattern.match(normalized)
        if m:
            return await _HANDLERS[handler](session, *m.groups())
    raise BddStepError(
        f"No Bubblegum BDD step matches: {text!r}. "
        "Use a quoted-argument phrasing (see bubblegum.bdd.dispatcher), or the "
        'raw passthrough: run "<plain English instruction>".'
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def _act(session: Any, instruction: str) -> Any:
    result = await session.act(instruction)
    status = getattr(result, "status", None)
    if status == "failed":
        message = "resolution/execution failed"
        error = getattr(result, "error", None)
        if error is not None and getattr(error, "message", None):
            message = error.message
        raise BddStepError(f'Step "{instruction}" failed: {message}')
    return result


async def _h_goto(session: Any, url: str) -> Any:
    return await session.goto(url)


async def _h_click(session: Any, target: str) -> Any:
    return await _act(session, f"Click {target}")


async def _h_enter(session: Any, value: str, field: str) -> Any:
    return await _act(session, f'Enter "{value}" into {field}')


async def _h_fill(session: Any, field: str, value: str) -> Any:
    return await _act(session, f'Enter "{value}" into {field}')


async def _h_select(session: Any, value: str, field: str) -> Any:
    return await _act(session, f"Select {value} from {field}")


async def _h_check(session: Any, target: str) -> Any:
    return await _act(session, f"Check {target}")


async def _h_uncheck(session: Any, target: str) -> Any:
    return await _act(session, f"Uncheck {target}")


async def _h_raw(session: Any, instruction: str) -> Any:
    return await _act(session, instruction)


async def _h_see(session: Any, target: str) -> None:
    if not await session.is_visible(target):
        raise BddStepError(f'Expected to see "{target}", but it was not visible.')


async def _h_not_see(session: Any, target: str) -> None:
    if await session.is_visible(target):
        raise BddStepError(f'Expected NOT to see "{target}", but it was visible.')


async def _h_checked(session: Any, target: str) -> None:
    if not await session.is_checked(target):
        raise BddStepError(f'Expected "{target}" to be checked, but it was not.')


async def _h_not_checked(session: Any, target: str) -> None:
    if await session.is_checked(target):
        raise BddStepError(f'Expected "{target}" to be unchecked, but it was checked.')


async def _h_has_value(session: Any, field: str, expected: str) -> None:
    actual = await session.selected_value(field)
    if actual != expected:
        raise BddStepError(
            f'Expected "{field}" to have value "{expected}", but got "{actual}".'
        )


async def _h_contains(session: Any, target: str, expected: str) -> None:
    result = await session.extract(f"Get text of {target}")
    value = ""
    found_target = getattr(result, "target", None)
    if found_target is not None:
        value = str(found_target.metadata.get("extracted_value", ""))
    if expected not in value:
        raise BddStepError(
            f'Expected "{target}" to contain "{expected}", but read "{value}".'
        )


_HANDLERS = {
    "goto": _h_goto,
    "click": _h_click,
    "enter": _h_enter,
    "fill": _h_fill,
    "select": _h_select,
    "check": _h_check,
    "uncheck": _h_uncheck,
    "raw": _h_raw,
    "see": _h_see,
    "not_see": _h_not_see,
    "checked": _h_checked,
    "not_checked": _h_not_checked,
    "has_value": _h_has_value,
    "contains": _h_contains,
}
