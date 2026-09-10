"""Parsing of a trailing "… and press <Key>" commit directive on a value-entry
step (used to add a token/tags item), and its gating."""

from __future__ import annotations

import pytest

from bubblegum.core.sdk import _extract_press_key


@pytest.mark.parametrize(
    "phrase,clean,key",
    [
        ('Enter "AutoM1" into Milestones and press Tab', 'Enter "AutoM1" into Milestones', "Tab"),
        ('Enter "AutoM1" into Milestones and press Enter', 'Enter "AutoM1" into Milestones', "Enter"),
        ('Type "X" into Tags then press Enter to add', 'Type "X" into Tags', "Enter"),
        ('Enter "x" into Field and hit Return', 'Enter "x" into Field', "Enter"),
        ('Enter "x" into Field, press Escape', 'Enter "x" into Field', "Escape"),
        ('Enter "x" into Field and press the Enter key', 'Enter "x" into Field', "Enter"),
    ],
)
def test_extracts_and_strips_commit_key(phrase, clean, key):
    got_clean, got_key = _extract_press_key(phrase)
    assert got_key == key
    assert got_clean == clean


@pytest.mark.parametrize(
    "phrase",
    [
        'Enter "John" into Name',            # plain value entry, no directive
        "Click the Save button",             # not a value-entry verb
        "Click Submit and press onward",     # "onward" is not a key
        "press Enter",                       # nothing meaningful remains
        'Enter "x" into Field and press the Submit button',  # a button, not a key
    ],
)
def test_leaves_non_directive_untouched(phrase):
    got_clean, got_key = _extract_press_key(phrase)
    assert got_key is None
    assert got_clean == phrase
