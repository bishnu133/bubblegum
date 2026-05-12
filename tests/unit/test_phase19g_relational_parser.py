from __future__ import annotations

import json

from bubblegum.core.parser.instruction import infer_action_type, parse_relational_intent


def test_helper_returns_none_for_plain_legacy_instruction() -> None:
    assert parse_relational_intent("Click Login") is None


def test_for_anchor_emits_same_row_as_text() -> None:
    payload = parse_relational_intent("Click Edit for Alice Johnson")
    assert payload is not None
    assert payload["relation_type"] == "same_row_as_text"
    assert payload["anchor_text"] == "Alice Johnson"
    assert payload["ambiguity_policy"] == "fail_on_ambiguous"


def test_within_modal_emits_modal_scope() -> None:
    payload = parse_relational_intent("Click Delete in the confirmation modal")
    assert payload is not None
    assert payload["relation_type"] == "within_modal"
    assert payload["scope_type"] == "modal"
    assert payload["scope_label"] == "confirmation modal"


def test_within_region_dropdown_emits_expected_fields() -> None:
    payload = parse_relational_intent("Select Singapore from the Country dropdown")
    assert payload is not None
    assert payload["relation_type"] == "within_region"
    assert payload["scope_type"] == "region"
    assert payload["scope_label"] == "Country"
    assert payload["control_kind_hint"] == "dropdown"


def test_check_label_emits_label_for_checkbox() -> None:
    payload = parse_relational_intent("Check Terms and Conditions")
    assert payload is not None
    assert payload["relation_type"] == "label_for"
    assert payload["control_kind_hint"] == "checkbox"
    assert payload["primary_target_text"] == "Terms and Conditions"


def test_capitalization_and_punctuation_safe() -> None:
    payload = parse_relational_intent("CLICK EDIT FOR Alice Johnson!!!")
    assert payload is not None
    assert payload["anchor_text"] == "Alice Johnson"


def test_complex_nested_or_multi_anchor_is_deferred() -> None:
    assert parse_relational_intent("Click Edit for Alice in the confirmation modal") is None


def test_helper_output_is_json_safe() -> None:
    payload = parse_relational_intent("checkbox Terms and Conditions")
    assert payload is not None
    dumped = json.dumps(payload)
    assert isinstance(dumped, str) and dumped


def test_legacy_action_type_inference_unchanged() -> None:
    assert infer_action_type("Click Login", {}) == "click"
    assert infer_action_type("Type email", {}) == "type"
