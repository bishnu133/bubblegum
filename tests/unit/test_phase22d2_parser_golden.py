"""Phase 22D-2: golden parser cases for the widget vocabulary.

Loads tests/benchmarks/web_widgets/parser_cases.json and asserts the
combined output of decompose() + parse_relational_intent() matches
each case's expected fields. Absent fields in `expected` are not
checked, so cases can be specific to whichever layer they target.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bubblegum.core.parser.instruction import (
    decompose,
    infer_action_type,
    parse_relational_intent,
)


_DATASET_PATH = (
    Path(__file__).resolve().parent.parent
    / "benchmarks"
    / "web_widgets"
    / "parser_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    data = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert isinstance(cases, list) and cases, "parser_cases.json must contain cases"
    return cases


def _run_one(case: dict[str, Any]) -> dict[str, Any]:
    instruction = case["instruction"]
    action_type = infer_action_type(instruction, {})
    parsed = decompose(instruction, {})
    relational = parse_relational_intent(instruction, action_type=action_type) or {}

    actual: dict[str, Any] = {
        "action_type": action_type,
        "target_phrase": parsed.target_phrase,
        "input_value": parsed.input_value,
        "control_kind_hint": relational.get("control_kind_hint", "none"),
        "relation_type": relational.get("relation_type", "none"),
    }
    if "anchor_text" in relational:
        actual["anchor_text"] = relational["anchor_text"]
    if "scope_label" in relational:
        actual["scope_label"] = relational["scope_label"]
    if "primary_target_text" in relational:
        actual["primary_target_text"] = relational["primary_target_text"]
    return actual


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_golden_parser_case(case: dict[str, Any]) -> None:
    expected = case["expected"]
    actual = _run_one(case)

    mismatches: list[str] = []
    for key, want in expected.items():
        got = actual.get(key)
        if got != want:
            mismatches.append(f"  {key}: expected {want!r}, got {got!r}")

    if mismatches:
        instruction = case["instruction"]
        body = "\n".join(mismatches)
        pytest.fail(
            f"Golden parser case '{case['id']}' failed for instruction:\n"
            f"  {instruction!r}\n"
            f"Mismatches:\n{body}\n"
            f"Full actual: {actual!r}"
        )


def test_dataset_has_expected_coverage() -> None:
    cases = _load_cases()
    case_ids = {c["id"] for c in cases}
    # Pin a minimum coverage so dataset shrinkage is loud.
    required = {
        "select-from-country-no-dropdown-word",
        "click-link",
        "click-radio",
        "check-checkbox-bare",
        "uncheck-checkbox",
        "toggle-switch",
        "upload-to-field",
        "attach-as-field",
        "check-that-is-verify",
        "leading-verb-click-beats-select-in-target",
        "leading-verb-open-becomes-click",
    }
    missing = required - case_ids
    assert not missing, f"Required golden cases removed from dataset: {missing}"
