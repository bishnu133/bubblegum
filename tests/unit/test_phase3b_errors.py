from __future__ import annotations

from bubblegum.core.grounding.errors import (
    AmbiguousTargetError,
    BubblegumError,
    LowConfidenceError,
    ResolutionFailedError,
    ValidationFailedError,
)
from bubblegum.core.schemas import ArtifactRef, ResolvedTarget


def _candidate(ref: str = 'role=button[name="Login"]', confidence: float = 0.9) -> ResolvedTarget:
    return ResolvedTarget(ref=ref, confidence=confidence, resolver_name="accessibility_tree")


def test_custom_errors_extend_bubblegum_error():
    assert issubclass(ResolutionFailedError, BubblegumError)
    assert issubclass(AmbiguousTargetError, BubblegumError)
    assert issubclass(LowConfidenceError, BubblegumError)
    assert issubclass(ValidationFailedError, BubblegumError)


def test_resolution_failed_error_preserves_fields_and_message():
    err = ResolutionFailedError(step="Click Login", message="No candidate found", resolver_name="exact_text")
    assert err.step == "Click Login"
    assert err.message == "No candidate found"
    assert err.resolver_name == "exact_text"
    assert "No candidate found" in str(err)


def test_ambiguous_target_error_fields_and_message_include_gap():
    candidates = [_candidate(confidence=0.91), _candidate(ref='role=button[name="Sign In"]', confidence=0.90)]
    err = AmbiguousTargetError(step="Click Login", candidates=candidates, gap=0.012)

    assert err.gap == 0.012
    assert err.candidates == candidates
    assert "0.012" in err.message
    assert "Click Login" in err.message


def test_low_confidence_error_preserves_best_confidence_and_count():
    candidates = [_candidate(confidence=0.41), _candidate(ref='text="Login"', confidence=0.39)]
    err = LowConfidenceError(step="Click Login", candidates=candidates, best_confidence=0.41)

    assert err.best_confidence == 0.41
    assert "0.41" in err.message
    assert "2 candidate" in err.message


def test_validation_failed_error_preserves_expected_actual_and_optional_fields():
    screenshot = ArtifactRef(type="screenshot", path="artifacts/fail.png", timestamp="2026-05-01T00:00:00Z")
    err = ValidationFailedError(
        step="Verify welcome text",
        expected="Welcome",
        actual="Hello",
        resolver_name="accessibility_tree",
        screenshot=screenshot,
    )

    assert err.expected == "Welcome"
    assert err.actual == "Hello"
    assert err.resolver_name == "accessibility_tree"
    assert err.screenshot == screenshot
    assert "expected 'Welcome', got 'Hello'" in err.message


def test_bubblegum_error_repr_contains_key_debug_fields():
    err = ResolutionFailedError(step="Click Login", message="boom", resolver_name="exact_text", candidates=[_candidate()])
    rep = repr(err)
    assert "ResolutionFailedError" in rep
    assert "Click Login" in rep
    assert "exact_text" in rep
    assert "candidates=1" in rep
