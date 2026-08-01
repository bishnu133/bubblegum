"""Status-indicator assertion: detection + value extraction (pure units)."""

from __future__ import annotations

import pytest

from bubblegum.core.sdk import _extract_status_value, _looks_like_status_assertion


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("the Workouts tag appeared as In Draft", "In Draft"),
        ("the Workouts tag appeared as Live", "Live"),
        ("status is In Draft", "In Draft"),
        ("the badge shows Active", "Active"),
        ("the page shows In Draft status", "In Draft"),
        ('Status is "Live"', "Live"),
        ("the item state is Published", "Published"),
        ("the chip reads Approved", "Approved"),
    ],
)
def test_extracts_status_value(phrase, expected):
    assert _looks_like_status_assertion(phrase, {}) is True
    assert _extract_status_value(phrase) == expected


@pytest.mark.parametrize(
    "phrase",
    [
        "Dashboard is visible",
        "the Create a Workout page appear",
        "the Save button is enabled",
        "the total is 42",
    ],
)
def test_non_status_phrases_not_matched(phrase):
    assert _looks_like_status_assertion(phrase, {}) is False


def test_explicit_assertion_type_status_forces_match():
    assert _looks_like_status_assertion("anything at all", {"assertion_type": "status"}) is True


def test_other_assertion_type_opts_out():
    assert _looks_like_status_assertion("status is Live", {"assertion_type": "table"}) is False
