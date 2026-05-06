from __future__ import annotations

from bubblegum.core.schemas import ErrorInfo, StepResult, ValidationResult


def verification_status(result: ValidationResult) -> str:
    return "passed" if result.passed else "failed"


def verification_error(expected_value, result: ValidationResult) -> ErrorInfo | None:
    if result.passed:
        return None
    return ErrorInfo(
        error_type="ValidationFailedError",
        message=f"Validation failed: expected={expected_value!r}, actual={result.actual_value!r}",
    )


def make_verification_result(*, status: str, instruction: str, target, traces, duration_ms: int, result: ValidationResult, error: ErrorInfo | None) -> StepResult:
    return StepResult(
        status=status,
        action=instruction,
        target=target,
        confidence=target.confidence,
        validation=result,
        duration_ms=duration_ms,
        traces=traces,
        error=error,
    )
