from __future__ import annotations

from pathlib import Path

from bubblegum.core.grounding.errors import LowConfidenceError
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
from bubblegum.core.schemas import ResolvedTarget, ResolverTrace
from scripts.run_benchmarks import (
    _build_deterministic_engine,
    _html_to_a11y_snapshot,
    _map_case_to_intent,
    load_cases,
    run_execution_validation,
    run_static_validation,
)


class FakeEngine:
    def __init__(self, winner: str = "exact_text", confidence: float = 0.95) -> None:
        self.winner = winner
        self.confidence = confidence
        self.intents = []

    async def ground(self, intent):
        self.intents.append(intent)
        target = ResolvedTarget(
            ref='text="x"',
            confidence=self.confidence,
            resolver_name=self.winner,
            metadata={},
        )
        traces = [
            ResolverTrace(
                resolver_name=self.winner,
                duration_ms=1,
                candidates=[target],
                can_run=True,
            )
        ]
        return target, traces


class LowConfidenceEngine:
    def __init__(self, candidates: list[ResolvedTarget]) -> None:
        self.candidates = candidates

    async def ground(self, intent):
        raise LowConfidenceError(
            step=intent.instruction,
            candidates=self.candidates,
            best_confidence=max(float(c.confidence) for c in self.candidates) if self.candidates else 0.0,
        )


class BoomEngine:
    async def ground(self, intent):
        raise RuntimeError("boom")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_static_validation_still_passes_current_fixtures() -> None:
    result = run_static_validation(_repo_root())
    assert result["ok"] is True
    assert result["total"] > 0


def test_execution_summary_shape_includes_skipped_and_executed() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case.pop("executable", None)
    case.pop("execute_skip_reason", None)
    cases = [case]
    engine = FakeEngine(winner="fuzzy_text", confidence=0.725)

    result = run_execution_validation(root, engine=engine, cases=cases)

    assert sorted(result.keys()) == ["diagnostics", "executed", "failed", "ok", "passed", "skipped", "success_rate", "total"]
    assert result["total"] == 1
    assert result["executed"] == 1
    assert result["skipped"] == 0
    assert len(result["diagnostics"]) == 1


def test_executable_false_cases_are_skipped_not_failed() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case["executable"] = False
    case["execute_skip_reason"] = "not executable"
    engine = FakeEngine()

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["failed"] == 0
    assert result["skipped"] == 1
    assert result["executed"] == 0
    assert result["diagnostics"][0]["status"] == "skipped"
    assert result["diagnostics"][0]["skip_reason"] == "not executable"
    assert len(engine.intents) == 0


def test_execution_uses_execute_expectation_override() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case.pop("executable", None)
    case.pop("execute_skip_reason", None)
    case["execute_expected_resolver_winner"] = "fuzzy_text"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = FakeEngine(winner="fuzzy_text", confidence=0.725)

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is True
    assert result["passed"] == 1


def test_execution_falls_back_to_static_expectations_when_execute_fields_absent() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    for key in ("execute_expected_resolver_winner", "execute_confidence_min", "execute_confidence_max"):
        case.pop(key, None)
    case.pop("executable", None)
    case.pop("execute_skip_reason", None)

    engine = FakeEngine(winner="exact_text", confidence=0.95)
    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is True
    assert result["passed"] == 1


def test_winner_mismatch_returns_failure() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case.pop("executable", None)
    case.pop("execute_skip_reason", None)
    case["execute_expected_resolver_winner"] = "exact_text"
    case["execute_confidence_min"] = 0.9
    case["execute_confidence_max"] = 1.0
    engine = FakeEngine(winner="fuzzy_text", confidence=0.95)

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is False
    assert result["failed"] == 1
    assert result["diagnostics"][0]["winner_ok"] is False


def test_confidence_out_of_range_returns_failure() -> None:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case.pop("executable", None)
    case.pop("execute_skip_reason", None)
    case["execute_expected_resolver_winner"] = "fuzzy_text"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = FakeEngine(winner="fuzzy_text", confidence=0.2)

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is False
    assert result["failed"] == 1
    assert result["diagnostics"][0]["confidence_ok"] is False


def test_web_fixture_maps_to_web_context() -> None:
    root = _repo_root()
    case = next(c for c in load_cases(root) if c["platform"] == "web")

    intent = _map_case_to_intent(case, root)

    assert intent.channel == "web"
    assert "a11y_snapshot" in intent.context
    assert "dom_snapshot" in intent.context
    assert "screen_signature" in intent.context
    assert intent.context["screen_signature"]
    assert intent.context["a11y_snapshot"].strip()
    assert "button" in intent.context["a11y_snapshot"]


def test_android_fixture_maps_to_mobile_hierarchy_xml_context() -> None:
    root = _repo_root()
    case = next(c for c in load_cases(root) if c["platform"] == "android")

    intent = _map_case_to_intent(case, root)

    assert intent.channel == "mobile"
    assert "hierarchy_xml" in intent.context
    assert "a11y_snapshot" not in intent.context
    assert "dom_snapshot" not in intent.context


def test_execution_uses_injected_engine_only() -> None:
    root = _repo_root()
    case_a = dict(load_cases(root)[0])
    case_b = dict(load_cases(root)[1])
    for c in (case_a, case_b):
        c["executable"] = True
        c["execute_expected_resolver_winner"] = "exact_text"
        c["execute_confidence_min"] = 0.9
        c["execute_confidence_max"] = 1.0
    engine = FakeEngine()

    result = run_execution_validation(root, engine=engine, cases=[case_a, case_b])

    assert result["total"] == 2
    assert result["executed"] == 2
    assert len(engine.intents) == 2


def test_execution_engine_excludes_tier3_ai_ocr_vision_resolvers() -> None:
    engine = _build_deterministic_engine()
    names = [r.name for r in engine.registry.all()]
    assert "llm_grounding" not in names
    assert "ocr" not in names
    assert "vision_model" not in names


def test_html_fixture_is_mapped_to_a11y_like_snapshot() -> None:
    html = "<html><body><button>Login</button><input aria-label='Email'/></body></html>"
    snap = _html_to_a11y_snapshot(html)
    assert snap.strip()
    assert 'button "Login"' in snap
    assert 'textbox "Email"' in snap


def test_execute_mode_produces_case_level_diagnostics_without_global_policy_error() -> None:
    root = _repo_root()
    cases = [dict(load_cases(root)[0]), dict(load_cases(root)[1])]
    for c in cases:
        c["executable"] = True
    result = run_execution_validation(root, cases=cases)
    assert result["total"] == 2
    assert len(result["diagnostics"]) == 2
    for row in result["diagnostics"]:
        assert "AICostPolicyBlockedError" not in str(row["error"])


def test_memory_precondition_case_resolves_through_memory_cache() -> None:
    root = _repo_root()
    case = next(c for c in load_cases(root) if c["id"] == "web_stale_selector_recovery_001")
    result = run_execution_validation(root, cases=[case])
    assert result["executed"] == 1
    assert result["passed"] == 1
    assert result["failed"] == 0
    assert result["diagnostics"][0]["actual_winner"] == "memory_cache"


def test_execute_mode_does_not_touch_repo_default_memory_db() -> None:
    root = _repo_root()
    db_path = root / ".bubblegum" / "memory.db"
    before = db_path.stat().st_mtime_ns if db_path.exists() else None
    case = next(c for c in load_cases(root) if c["id"] == "web_stale_selector_recovery_001")

    _ = run_execution_validation(root, cases=[case])

    after = db_path.stat().st_mtime_ns if db_path.exists() else None
    assert before == after


def test_deterministic_engine_uses_memory_cache_with_ephemeral_db() -> None:
    engine = _build_deterministic_engine()
    memory = next(r for r in engine.registry.all() if r.name == "memory_cache")
    assert isinstance(memory, MemoryCacheResolver)
    assert "benchmark_memory.db" in str(memory._layer._db_path)


def _base_execute_case() -> tuple[Path, dict]:
    root = _repo_root()
    case = dict(load_cases(root)[0])
    case["executable"] = True
    return root, case


def test_execute_allow_review_true_converts_low_confidence_to_review_pass() -> None:
    root, case = _base_execute_case()
    case["execute_allow_review"] = True
    case["execute_expected_resolver_winner"] = "appium_hierarchy"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = LowConfidenceEngine(
        candidates=[
            ResolvedTarget(ref="//bad", confidence=0.5, resolver_name="exact_text"),
            ResolvedTarget(ref="//ok", confidence=0.72, resolver_name="appium_hierarchy"),
        ]
    )

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is True
    row = result["diagnostics"][0]
    assert row["status"] == "pass"
    assert row["review_candidate_used"] is True
    assert row["review_candidate_winner"] == "appium_hierarchy"
    assert row["review_candidate_confidence"] == 0.72
    assert row["status_detail"] == "review_pass"


def test_execute_allow_review_false_keeps_low_confidence_as_failure() -> None:
    root, case = _base_execute_case()
    case["execute_allow_review"] = False
    case["execute_expected_resolver_winner"] = "appium_hierarchy"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = LowConfidenceEngine(
        candidates=[ResolvedTarget(ref="//ok", confidence=0.72, resolver_name="appium_hierarchy")]
    )

    result = run_execution_validation(root, engine=engine, cases=[case])

    assert result["ok"] is False
    row = result["diagnostics"][0]
    assert row["status"] == "fail"
    assert row["review_candidate_used"] is False
    assert "LowConfidenceError" in str(row["error"])


def test_review_pass_respects_expected_resolver_winner() -> None:
    root, case = _base_execute_case()
    case["execute_allow_review"] = True
    case["execute_expected_resolver_winner"] = "exact_text"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = LowConfidenceEngine(
        candidates=[ResolvedTarget(ref="//ok", confidence=0.72, resolver_name="appium_hierarchy")]
    )

    result = run_execution_validation(root, engine=engine, cases=[case])
    row = result["diagnostics"][0]
    assert row["status"] == "fail"
    assert row["winner_ok"] is False
    assert row["review_candidate_used"] is True
    assert row["status_detail"] == "review_fail"


def test_review_pass_respects_confidence_range() -> None:
    root, case = _base_execute_case()
    case["execute_allow_review"] = True
    case["execute_expected_resolver_winner"] = "appium_hierarchy"
    case["execute_confidence_min"] = 0.7
    case["execute_confidence_max"] = 0.8
    engine = LowConfidenceEngine(
        candidates=[ResolvedTarget(ref="//ok", confidence=0.65, resolver_name="appium_hierarchy")]
    )

    result = run_execution_validation(root, engine=engine, cases=[case])
    row = result["diagnostics"][0]
    assert row["status"] == "fail"
    assert row["confidence_ok"] is False
    assert row["review_candidate_used"] is True
    assert row["review_candidate_confidence"] == 0.65


def test_non_low_confidence_error_still_fails_normally() -> None:
    root, case = _base_execute_case()
    case["execute_allow_review"] = True
    case["execute_expected_resolver_winner"] = "exact_text"
    case["execute_confidence_min"] = 0.9
    case["execute_confidence_max"] = 1.0

    result = run_execution_validation(root, engine=BoomEngine(), cases=[case])
    row = result["diagnostics"][0]
    assert row["status"] == "fail"
    assert row["review_candidate_used"] is False
    assert row["status_detail"] == "exception_fail"
    assert "RuntimeError" in str(row["error"])
