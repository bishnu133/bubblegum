"""Unit tests for trailing positional-context stripping during target isolation.

"Click the Save button on the Challenges page" should resolve against "Save",
not "Save ... on the Challenges page". The locational tail is noise that dilutes
text matching, so the rule-based parser strips it — while leaving bare region
names and meaningful relational scopes (modal/dropdown) intact.
"""

from __future__ import annotations

import pytest

from bubblegum.core.parser import decompose


@pytest.mark.parametrize(
    "instruction,expected_target",
    [
        ("Click the Customer Care menu in the top navigation bar", "Customer Care menu"),
        ("Click the Challenges menu in the header", "Challenges menu"),
        ("Click the Save button on the Challenges page", "Save"),
        ("Click Sign In in the header", "Sign In"),
        ("Click Profile in the top nav bar", "Profile"),
        ("Click Settings in the sidebar", "Settings"),
        ("Click Logout in the footer", "Logout"),
        ("Tap Submit on the page", "Submit"),
        ("Click Home in the navigation bar", "Home"),
        ("Click Help in the toolbar", "Help"),
    ],
)
def test_trailing_context_is_stripped(instruction, expected_target):
    parsed = decompose(instruction, {})
    assert parsed.target_phrase == expected_target


@pytest.mark.parametrize(
    "instruction,expected_target",
    [
        # Bare region name with no preposition: it's the actual target, keep it.
        ("Click the Header", "Header"),
        ("Click Footer", "Footer"),
        # Region words mid-phrase (not a trailing positional tail) survive.
        ("Click the Page Settings link", "Page Settings"),
        ("Click the Header Logo", "Header Logo"),
    ],
)
def test_meaningful_targets_are_preserved(instruction, expected_target):
    parsed = decompose(instruction, {})
    assert parsed.target_phrase == expected_target


def test_context_strip_then_widget_suffix():
    # Both isolation steps compose: drop the page tail AND the widget suffix.
    parsed = decompose("Click the Save button on the Challenges page", {})
    assert parsed.target_phrase == "Save"
