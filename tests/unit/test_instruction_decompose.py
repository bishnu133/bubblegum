"""Unit tests for natural-language instruction decomposition.

Verifies the deterministic grammar splits an instruction into
(action_type, target_phrase, input_value) so callers no longer have to supply
selector / input_value manually.
"""

from __future__ import annotations

import pytest

from bubblegum.core.parser import decompose


@pytest.mark.parametrize(
    "instruction,action,target,value",
    [
        ('Enter "tomsmith" into Username', "type", "Username", "tomsmith"),
        ("Type tomsmith into the search box", "type", "search box", "tomsmith"),
        ("Fill 'secret' in Password", "type", "Password", "secret"),
        ("Select California from State", "select", "State", "California"),
        ("Click Login", "click", "Login", None),
        ("Tap the Submit button", "tap", "Submit button", None),
        ("Verify Dashboard is visible", "verify", "Dashboard is visible", None),
    ],
)
def test_decompose_grammar(instruction, action, target, value):
    parsed = decompose(instruction, {})
    assert parsed.action_type == action
    assert parsed.target_phrase == target
    assert parsed.input_value == value
    assert parsed.confident is True


def test_value_is_not_mistaken_for_target():
    # Regression: the quoted value must not become the target phrase.
    parsed = decompose('Enter "tomsmith" into Username', {})
    assert parsed.target_phrase == "Username"
    assert parsed.input_value == "tomsmith"


def test_explicit_kwargs_value_with_bare_field():
    parsed = decompose("Username", {"input_value": "tomsmith", "action_type": "type"})
    assert parsed.input_value == "tomsmith"
    assert parsed.target_phrase == "Username"


def test_ambiguous_type_is_not_confident():
    # No target separator and no explicit value -> defer to LLM fallback.
    parsed = decompose("Type tomsmith", {})
    assert parsed.confident is False
