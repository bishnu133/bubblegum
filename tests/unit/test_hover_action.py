"""Unit coverage for the web `hover` action (reveal hover-triggered menus)."""

from __future__ import annotations

import pytest

from bubblegum.adapters.web.playwright.adapter import _ACTION_DISPATCH, PlaywrightAdapter
from bubblegum.core.grounding.signals import role_fit_score
from bubblegum.core.parser.instruction import decompose
from bubblegum.core.schemas import ActionPlan


@pytest.mark.parametrize(
    "instruction,expected_target",
    [
        ("Hover over the Profile menu", "Profile menu"),
        ("Hover the Create button", "Create"),
        ('Hover "+ Create a challenge"', "+ Create a challenge"),
        ('Hover over "+ Create a challenge"', "+ Create a challenge"),
    ],
)
def test_parser_maps_hover_and_isolates_target(instruction, expected_target):
    parsed = decompose(instruction)
    assert parsed.action_type == "hover"
    assert parsed.target_phrase == expected_target


def test_click_target_extraction_unchanged():
    # Guard: adding hover must not regress the generic click path.
    assert decompose("Click the Login button").target_phrase == "Login"


def test_actionplan_accepts_hover():
    assert ActionPlan(action_type="hover", target_hint="Menu").action_type == "hover"


def test_hover_is_in_dispatch_table():
    assert "hover" in _ACTION_DISPATCH


def test_hover_prefers_interactive_roles_over_text():
    # Guards the antd `ant-dropdown-trigger` case: a <button> must outrank its
    # inner text <span> for hover, so the two don't tie into an ambiguous error.
    assert role_fit_score("button", "hover") == 1.0
    assert role_fit_score("combobox", "hover") == 1.0
    assert role_fit_score("", "hover") == 0.0
    assert role_fit_score("button", "hover") > role_fit_score("", "hover")


@pytest.mark.asyncio
async def test_do_hover_calls_locator_hover_with_timeout():
    class _FakeLocator:
        def __init__(self) -> None:
            self.hovered = False
            self.timeout = None

        async def hover(self, timeout=None):
            self.hovered = True
            self.timeout = timeout

    adapter = PlaywrightAdapter.__new__(PlaywrightAdapter)  # no real browser needed
    locator = _FakeLocator()
    await adapter._do_hover(ActionPlan(action_type="hover", target_hint="Menu"), locator, 5000)
    assert locator.hovered is True
    assert locator.timeout == 5000
