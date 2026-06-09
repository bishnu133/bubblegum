"""Phase 22E-5: Tier 2 widgets — parser + adapter dispatch.

Covers:
  - Parser: "Click X tab" / "Expand X section" / "Open X accordion"
    set the right kind_hint and strip the trailing widget word.
  - Parser: "Set X to N" (target-first) yields action=set with target=X
    and value=N — NOT value=X like type/enter would.
  - Parser: "Set X slider to N" still strips the slider suffix.
  - role_fit_score: action=set prefers slider / spinbutton.
  - kind alignment maps slider → {slider, spinbutton} in both resolvers.
  - Adapter dispatch covers "set" → _do_set; _do_set sets value + fires
    input/change events; raises without input_value.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bubblegum.core.elements.query import ControlKind, KNOWN_CONTROL_KINDS
from bubblegum.core.grounding.resolvers.accessibility_tree import (
    _KIND_ROLE_ALIGNMENT as _A11Y_KIND_ALIGNMENT,
)
from bubblegum.core.grounding.resolvers.fuzzy_text import (
    _KIND_ROLE_ALIGNMENT as _FUZZY_KIND_ALIGNMENT,
)
from bubblegum.core.grounding.signals import role_fit_score
from bubblegum.core.parser.instruction import (
    decompose,
    parse_relational_intent,
)
from bubblegum.core.schemas import ActionPlan


# ---------------------------------------------------------------------------
# ControlKind
# ---------------------------------------------------------------------------


def test_slider_added_to_control_kind_vocabulary():
    assert "slider" in KNOWN_CONTROL_KINDS
    assert ControlKind.SLIDER == "slider"


# ---------------------------------------------------------------------------
# Tabs / accordion parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction, target",
    [
        ("Click Profile tab", "Profile"),
        ("Click the Profile tab", "Profile"),
        ("Open Settings tab", "Settings"),
    ],
)
def test_click_tab_strips_suffix_and_sets_tab_hint(instruction, target):
    p = decompose(instruction)
    assert p.action_type == "click"
    assert p.target_phrase == target
    assert p.confident is True

    rel = parse_relational_intent(instruction, action_type=p.action_type)
    assert rel is not None
    assert rel["control_kind_hint"] == "tab"
    assert rel["primary_target_text"] == target


@pytest.mark.parametrize(
    "instruction, target",
    [
        ("Expand Billing section", "Billing"),
        ("Collapse Account panel", "Account"),
        ("Open Billing accordion", "Billing"),
    ],
)
def test_expand_section_uses_button_hint(instruction, target):
    p = decompose(instruction)
    # expand/collapse map to click (the header is a button).
    assert p.action_type == "click"
    assert p.target_phrase == target

    rel = parse_relational_intent(instruction, action_type=p.action_type)
    assert rel is not None
    assert rel["control_kind_hint"] == "button"
    assert rel["primary_target_text"] == target


# ---------------------------------------------------------------------------
# Slider parsing — "Set X to N" reverses the value/target order
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction, target, value",
    [
        ("Set Volume to 75", "Volume", "75"),
        ("Set the Brightness to 50", "Brightness", "50"),
        ("Set Volume slider to 25", "Volume", "25"),
        ('Set Volume to "75"', "Volume", "75"),
    ],
)
def test_set_target_to_value_parses_correctly(instruction, target, value):
    p = decompose(instruction)
    assert p.action_type == "set"
    assert p.target_phrase == target
    assert p.input_value == value
    assert p.confident is True

    rel = parse_relational_intent(instruction, action_type=p.action_type)
    assert rel is not None
    assert rel["control_kind_hint"] == "slider"
    assert rel["primary_target_text"] == target


def test_enter_into_field_still_value_first():
    # Regression: "set" shares a regex namespace with "enter" — make sure
    # the existing value-into-target grammar still wins for type-style verbs.
    p = decompose("Enter 75 into Volume")
    assert p.action_type == "type"
    assert p.target_phrase == "Volume"
    assert p.input_value == "75"


# ---------------------------------------------------------------------------
# Signal weights / kind alignment
# ---------------------------------------------------------------------------


def test_role_fit_score_for_set_prefers_slider_family():
    assert role_fit_score("slider", "set") == 1.0
    assert role_fit_score("spinbutton", "set") == 1.0
    assert 0 < role_fit_score("textbox", "set") < 1.0
    assert role_fit_score("button", "set") == 0.0


def test_kind_alignment_has_slider_entry_in_both_resolvers():
    assert _A11Y_KIND_ALIGNMENT["slider"] == frozenset({"slider", "spinbutton"})
    assert _FUZZY_KIND_ALIGNMENT["slider"] == frozenset({"slider", "spinbutton"})


# ---------------------------------------------------------------------------
# Adapter — _do_set
# ---------------------------------------------------------------------------


class _FakeLocator:
    """Minimal Playwright locator surface for _do_set."""

    def __init__(self):
        self.waited_for: list[dict] = []
        self.evaluate_calls: list[tuple[str, Any]] = []

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def wait_for(self, **kwargs):
        self.waited_for.append(kwargs)

    async def evaluate(self, script: str, *args):
        self.evaluate_calls.append((script, args[0] if args else None))


def test_do_set_evaluates_value_and_dispatches_events():
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    adapter = PlaywrightAdapter(page=object())
    locator = _FakeLocator()
    plan = ActionPlan(action_type="set", target_hint="Volume", input_value="75")

    asyncio.run(adapter._do_set(plan, locator, timeout=2_000))

    assert len(locator.evaluate_calls) == 1
    script, value = locator.evaluate_calls[0]
    assert value == "75"
    # Script must set value and dispatch input + change events.
    assert "input.value = v" in script
    assert "dispatchEvent" in script
    assert "new Event('input'" in script
    assert "new Event('change'" in script
    assert locator.waited_for == [{"state": "attached", "timeout": 2_000}]


def test_do_set_requires_input_value():
    from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter

    adapter = PlaywrightAdapter(page=object())
    plan = ActionPlan(action_type="set", target_hint="Volume", input_value=None)
    with pytest.raises(ValueError, match="input_value"):
        asyncio.run(adapter._do_set(plan, _FakeLocator(), timeout=1_000))


def test_set_action_in_dispatch_table():
    from bubblegum.adapters.web.playwright.adapter import _ACTION_DISPATCH

    assert "set" in _ACTION_DISPATCH
