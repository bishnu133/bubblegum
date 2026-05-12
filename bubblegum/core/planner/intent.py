from __future__ import annotations

from typing import Any

from bubblegum.core.parser.instruction import parse_relational_intent
from bubblegum.core.schemas import ContextRequest, ExecutionOptions, StepIntent, ValidationPlan


def build_options(kwargs: dict, *, ai_enabled: bool, max_cost_level: str, memory_ttl_days: int, memory_max_failures: int) -> ExecutionOptions:
    known = {
        "timeout_ms",
        "retry_count",
        "wait_for",
        "use_ai",
        "max_cost_level",
        "memory_ttl_days",
        "memory_max_failures",
    }
    opts = {k: v for k, v in kwargs.items() if k in known}
    opts.setdefault("use_ai", ai_enabled)
    opts.setdefault("max_cost_level", max_cost_level)
    opts.setdefault("memory_ttl_days", memory_ttl_days)
    opts.setdefault("memory_max_failures", memory_max_failures)
    return ExecutionOptions(**opts)


def make_intent(*, instruction: str, channel: str, platform: str, action_type: str, options: ExecutionOptions, selector: str | None = None) -> StepIntent:
    context: dict[str, Any] = {"explicit_selector": selector} if selector else {}
    relational_intent = parse_relational_intent(instruction, action_type=action_type)
    if relational_intent is not None:
        context["relational_intent"] = relational_intent

    return StepIntent(
        instruction=instruction,
        channel=channel,
        platform=platform,
        action_type=action_type,
        context=context,
        options=options,
    )


def context_request() -> ContextRequest:
    return ContextRequest(include_screenshot=False)


def build_validation_plan(*, assertion_type: str, expected_value: Any, timeout_ms: int) -> ValidationPlan:
    return ValidationPlan(assertion_type=assertion_type, expected_value=expected_value, timeout_ms=timeout_ms)
