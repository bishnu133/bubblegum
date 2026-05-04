from __future__ import annotations

from bubblegum.core.schemas import (
    ActionPlan,
    ArtifactRef,
    ErrorInfo,
    ExecutionOptions,
    ResolvedTarget,
    ResolverTrace,
    StepIntent,
    StepResult,
    ValidationPlan,
)


def test_step_intent_nested_execution_options_round_trip():
    intent = StepIntent(
        instruction="Click Login",
        channel="web",
        action_type="click",
        context={"screen_signature": "abc123", "explicit_selector": "#login"},
        options=ExecutionOptions(
            timeout_ms=20000,
            retry_count=4,
            wait_for="domcontentloaded",
            use_ai=False,
            max_cost_level="low",
            memory_ttl_days=14,
            memory_max_failures=5,
        ),
    )

    dumped = intent.model_dump(mode="json")
    restored = StepIntent.model_validate(dumped)

    assert restored == intent
    assert isinstance(dumped, dict)
    assert dumped["options"]["timeout_ms"] == 20000


def test_step_result_round_trip_with_nested_error_trace_artifacts():
    target = ResolvedTarget(ref='role=button[name="Login"]', confidence=0.93, resolver_name="accessibility_tree")
    artifact = ArtifactRef(type="screenshot", path="artifacts/login.png", timestamp="2026-05-01T00:00:00Z")
    trace = ResolverTrace(resolver_name="exact_text", duration_ms=12, candidates=[target], can_run=True)
    err = ErrorInfo(error_type="LowConfidenceError", message="too low", resolver_name="exact_text", candidates=[target], screenshot=artifact)

    result = StepResult(
        status="failed",
        action="Click Login",
        target=target,
        confidence=0.42,
        artifacts=[artifact],
        duration_ms=123,
        error=err,
        traces=[trace],
    )

    dumped = result.model_dump(mode="json")
    restored = StepResult.model_validate(dumped)

    assert restored == result
    assert dumped["error"]["error_type"] == "LowConfidenceError"
    assert dumped["traces"][0]["resolver_name"] == "exact_text"


def test_action_and_validation_plan_defaults_are_stable():
    plan = ActionPlan(action_type="click")
    vplan = ValidationPlan(assertion_type="text_visible")

    assert plan.target_hint is None
    assert plan.input_value is None
    assert plan.options.timeout_ms == 10000
    assert plan.options.max_cost_level == "medium"

    assert vplan.expected_value is None
    assert vplan.timeout_ms == 5000


def test_schema_dumps_are_json_safe_primitives():
    intent = StepIntent(instruction="Type email", channel="web", action_type="type")
    dumped = intent.model_dump(mode="json")

    assert isinstance(dumped["instruction"], str)
    assert isinstance(dumped["options"]["retry_count"], int)
    assert dumped["context"] == {}
