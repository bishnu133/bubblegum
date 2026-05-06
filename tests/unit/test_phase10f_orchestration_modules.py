from bubblegum.core.parser import extract_expected, infer_action_type
from bubblegum.core.planner import build_options, build_validation_plan, make_intent
from bubblegum.core.recovery import remove_explicit_selector, used_explicit_selector
from bubblegum.core.validation import verification_error, verification_status
from bubblegum.core.schemas import ValidationResult


def test_parser_infer_action_type_parity():
    assert infer_action_type("Click Login", {}) == "click"
    assert infer_action_type("Type email", {}) == "type"
    assert infer_action_type("Verify dashboard visible", {}) == "verify"
    assert infer_action_type("Read account id", {}) == "extract"


def test_parser_extract_expected_parity():
    assert extract_expected("Verify Welcome banner") == "Welcome banner"


def test_planner_build_options_defaults_parity():
    opts = build_options({}, ai_enabled=True, max_cost_level="medium", memory_ttl_days=7, memory_max_failures=2)
    assert opts.use_ai is True
    assert opts.max_cost_level == "medium"
    assert opts.memory_ttl_days == 7
    assert opts.memory_max_failures == 2


def test_planner_make_intent_sets_selector_context():
    opts = build_options({}, ai_enabled=True, max_cost_level="medium", memory_ttl_days=7, memory_max_failures=2)
    intent = make_intent(instruction="Click", channel="web", platform="web", action_type="click", selector="#x", options=opts)
    assert intent.context["explicit_selector"] == "#x"


def test_validation_helpers_parity():
    vr = ValidationResult(passed=False, actual_value="x", duration_ms=1)
    assert verification_status(vr) == "failed"
    err = verification_error("y", vr)
    assert err is not None and err.error_type == "ValidationFailedError"


def test_recovery_helpers_parity():
    assert used_explicit_selector(resolver_name="explicit_selector", failed_selector="#x", ref="#x")
    ctx = {"explicit_selector": "#x"}
    remove_explicit_selector(ctx)
    assert "explicit_selector" not in ctx


def test_build_validation_plan_parity():
    plan = build_validation_plan(assertion_type="text_visible", expected_value="Hello", timeout_ms=5000)
    assert plan.assertion_type == "text_visible"
    assert plan.expected_value == "Hello"
