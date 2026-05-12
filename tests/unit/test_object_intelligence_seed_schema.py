from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "tests" / "benchmarks" / "object_intelligence" / "seed_cases.json"
SCHEMA_PATH = ROOT / "tests" / "benchmarks" / "object_intelligence" / "schema.json"
REGRESSION_CASES_PATH = ROOT / "tests" / "benchmarks" / "fixtures" / "cases.json"

REQUIRED_TOP_FIELDS = {
    "case_id",
    "category",
    "channel",
    "platform_framework",
    "fixture_path",
    "instruction",
    "action_type",
    "target_text",
    "expected_target",
    "acceptable_refs",
    "expected_relation",
    "expected_graph_signals",
    "expected_confidence_range",
    "expected_failure_mode",
    "baseline_expectations",
    "tags",
}

REQUIRED_BASELINE_KEYS = {
    "bubblegum_current",
    "playwright_raw_role_text",
    "llm_vision_raw",
    "manual_expected",
}

DISALLOWED_PAYLOAD_PATTERNS = ("base64", "data:image", "screenshot", "payload", "graph_dump", "full_graph")


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_seed_and_schema_files_exist() -> None:
    assert SEED_PATH.exists(), f"Missing seed file: {SEED_PATH}"
    assert SCHEMA_PATH.exists(), f"Missing schema file: {SCHEMA_PATH}"


def test_seed_cases_have_required_shape_and_constraints() -> None:
    payload = _load_json(SEED_PATH)
    assert "cases" in payload and isinstance(payload["cases"], list) and payload["cases"], "cases must be non-empty list"

    seen_ids: set[str] = set()
    for case in payload["cases"]:
        assert REQUIRED_TOP_FIELDS.issubset(case.keys()), f"Missing required fields in case: {case.get('case_id')}"
        assert ("expected_resolver" in case) or ("allowed_resolvers" in case), (
            f"Case {case.get('case_id')} must include expected_resolver or allowed_resolvers"
        )

        case_id = case["case_id"]
        assert case_id not in seen_ids, f"Duplicate case_id: {case_id}"
        seen_ids.add(case_id)

        fixture_path = case["fixture_path"]
        assert isinstance(fixture_path, str) and fixture_path.strip(), f"Invalid fixture_path for case {case_id}"
        assert not fixture_path.startswith("/"), f"fixture_path must be relative: {case_id}"
        assert ".." not in fixture_path, f"fixture_path must not contain parent traversal: {case_id}"

        baseline = case["baseline_expectations"]
        assert isinstance(baseline, dict), f"baseline_expectations must be object: {case_id}"
        assert REQUIRED_BASELINE_KEYS.issubset(baseline.keys()), f"Missing baseline keys in {case_id}"

        graph_signals = case["expected_graph_signals"]
        assert isinstance(graph_signals, dict), f"expected_graph_signals must be object: {case_id}"
        assert len(graph_signals) <= 12, f"expected_graph_signals too large for seed case: {case_id}"
        for k, v in graph_signals.items():
            assert isinstance(k, str) and k.strip(), f"Invalid graph signal key in {case_id}"
            assert isinstance(v, (bool, str)), f"Graph signal values must be bool/string-like in {case_id}"
            if isinstance(v, str):
                assert v in {"true", "false", "n/a"}, f"Invalid graph signal string value in {case_id}: {v}"

        failure_mode = case["expected_failure_mode"]
        acceptable_refs = case["acceptable_refs"]
        is_negative = failure_mode is not None
        if is_negative:
            assert failure_mode in {
                "no_candidate",
                "wrong_candidate",
                "ambiguous_candidate",
                "low_confidence",
                "validation_mismatch",
                "stale_after_resolution",
                "action_intercepted",
                "unsupported_surface",
                "provider_or_vision_unavailable",
                "hydration_failed",
            }, f"Unsupported failure mode in {case_id}"
        else:
            assert isinstance(acceptable_refs, list) and len(acceptable_refs) > 0, (
                f"Positive case must include non-empty acceptable_refs: {case_id}"
            )

        raw = json.dumps(case).lower()
        for bad in DISALLOWED_PAYLOAD_PATTERNS:
            assert bad not in raw, f"Disallowed payload-like content '{bad}' in {case_id}"


def test_existing_regression_benchmark_path_remains_untouched() -> None:
    assert REGRESSION_CASES_PATH.exists(), "Regression benchmark file must remain present"
    assert str(REGRESSION_CASES_PATH).endswith("tests/benchmarks/fixtures/cases.json")


def test_schema_contains_required_baseline_keys() -> None:
    schema = _load_json(SCHEMA_PATH)
    case_props = schema["properties"]["cases"]["items"]["properties"]
    baseline = case_props["baseline_expectations"]["required"]
    assert set(baseline) == REQUIRED_BASELINE_KEYS
