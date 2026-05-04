import json
from pathlib import Path


REQUIRED_CATEGORIES = {
    "web_click_exact_text",
    "web_click_accessibility_role",
    "web_type_input",
    "web_select_dropdown",
    "web_verify_text",
    "web_ambiguous_text",
    "web_stale_selector_recovery",
    "android_tap_text",
    "android_tap_content_desc",
    "android_type_input",
    "android_scroll_to_target",
    "android_verify_text",
}


def _load_schema_and_cases() -> tuple[dict, list[dict], Path]:
    root = Path(__file__).resolve().parents[2]
    fixtures_dir = root / "tests/benchmarks/fixtures"
    schema = json.loads((fixtures_dir / "schema.json").read_text(encoding="utf-8"))
    cases = json.loads((fixtures_dir / "cases.json").read_text(encoding="utf-8"))
    return schema, cases, fixtures_dir


def test_cases_json_conforms_to_schema_shape() -> None:
    schema, cases, _ = _load_schema_and_cases()
    required = set(schema["required"])
    properties = set(schema["properties"].keys())

    assert isinstance(cases, list)
    assert cases, "cases.json should include at least one case"

    for case in cases:
        assert required.issubset(case.keys())
        assert set(case.keys()).issubset(properties)
        assert case["platform"] in {"web", "android"}
        assert 0 <= case["confidence_min"] <= case["confidence_max"] <= 1


def test_every_case_references_existing_snapshot_file() -> None:
    _, cases, fixtures_dir = _load_schema_and_cases()
    for case in cases:
        snapshot = fixtures_dir / case["snapshot_path"]
        assert snapshot.exists(), f"missing snapshot for case {case['id']}: {snapshot}"


def test_expected_winner_and_confidence_fields_present() -> None:
    _, cases, _ = _load_schema_and_cases()
    for case in cases:
        assert case["expected_resolver_winner"]
        assert "confidence_min" in case
        assert "confidence_max" in case


def test_optional_execute_fields_validate_when_present() -> None:
    _, cases, _ = _load_schema_and_cases()
    for case in cases:
        if "execute_confidence_min" in case or "execute_confidence_max" in case:
            assert "execute_confidence_min" in case
            assert "execute_confidence_max" in case
            assert 0 <= case["execute_confidence_min"] <= case["execute_confidence_max"] <= 1


def test_executable_false_requires_skip_reason() -> None:
    _, cases, _ = _load_schema_and_cases()
    for case in cases:
        if case.get("executable") is False:
            assert case.get("execute_skip_reason")


def test_executable_true_requires_execute_expectations() -> None:
    _, cases, _ = _load_schema_and_cases()
    for case in cases:
        if case.get("executable") is True:
            assert case.get("execute_expected_resolver_winner")
            assert "execute_confidence_min" in case
            assert "execute_confidence_max" in case
            assert 0 <= case["execute_confidence_min"] <= case["execute_confidence_max"] <= 1


def test_all_required_categories_present() -> None:
    _, cases, _ = _load_schema_and_cases()
    present = {case["category"] for case in cases}
    assert REQUIRED_CATEGORIES.issubset(present)


def test_memory_seed_preconditions_shape_when_present() -> None:
    _, cases, _ = _load_schema_and_cases()
    for case in cases:
        pre = case.get("preconditions")
        if not pre:
            continue
        seed = pre.get("memory_seed")
        if not seed:
            continue
        assert seed.get("ref")
        assert "confidence" in seed
        assert 0 <= seed["confidence"] <= 1
        assert seed.get("resolver_name")
