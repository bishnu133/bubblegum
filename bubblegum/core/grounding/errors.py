"""
bubblegum/core/grounding/errors.py
====================================
Full Bubblegum error taxonomy.

All errors extend BubblegumError. Every error carries structured context:
  - step instruction
  - resolver_name (if applicable)
  - candidates found (as ResolvedTarget list)
  - screenshot artifact reference (set post-construction when available)

Usage:
    raise ResolutionFailedError(step="Click Login", message="No candidate found")
    raise AmbiguousTargetError(step="Click Login", candidates=[t1, t2], gap=0.02)
"""

from __future__ import annotations

from bubblegum.core.schemas import ArtifactRef, ResolvedTarget


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BubblegumError(Exception):
    """
    Base class for all Bubblegum errors.

    Attributes:
        step        — the natural-language instruction that triggered this error
        message     — human-readable description
        resolver_name — which resolver raised/detected the condition (if applicable)
        candidates  — list of ResolvedTarget candidates found before the error
        screenshot  — ArtifactRef captured at the moment of failure (attached later)
    """

    def __init__(
        self,
        step:          str,
        message:       str,
        resolver_name: str | None           = None,
        candidates:    list[ResolvedTarget] | None = None,
        screenshot:    ArtifactRef | None   = None,
    ) -> None:
        super().__init__(message)
        self.step          = step
        self.message       = message
        self.resolver_name = resolver_name
        self.candidates    = candidates or []
        self.screenshot    = screenshot

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"step={self.step!r}, "
            f"message={self.message!r}, "
            f"resolver={self.resolver_name!r}, "
            f"candidates={len(self.candidates)})"
        )


# ---------------------------------------------------------------------------
# Resolution errors (raised by GroundingEngine / resolvers)
# ---------------------------------------------------------------------------

class ResolutionFailedError(BubblegumError):
    """
    All resolvers exhausted — no candidate found above the reject threshold.
    Raised when intent.context has no matching element whatsoever.
    """


class AmbiguousTargetError(BubblegumError):
    """
    Multiple candidates within ambiguous_gap (default 0.05) confidence of each other.
    Bubblegum refuses to auto-execute. Test author must disambiguate the step.

    Extra attributes:
        gap — the actual confidence gap between the top 2 candidates
    """

    def __init__(
        self,
        step:       str,
        candidates: list[ResolvedTarget],
        gap:        float,
        screenshot: ArtifactRef | None = None,
    ) -> None:
        message = (
            f"Ambiguous target for '{step}': "
            f"top 2 candidates within {gap:.3f} confidence gap "
            f"(threshold {0.05}). Refusing to auto-execute."
        )
        super().__init__(step=step, message=message, candidates=candidates, screenshot=screenshot)
        self.gap = gap


class LowConfidenceError(BubblegumError):
    """
    A candidate was found but its confidence is below reject_threshold (default 0.50).
    Raised after all eligible tiers have been exhausted.

    Extra attributes:
        best_confidence — the highest confidence score seen across all candidates
    """

    def __init__(
        self,
        step:            str,
        candidates:      list[ResolvedTarget],
        best_confidence: float,
        screenshot:      ArtifactRef | None = None,
    ) -> None:
        message = (
            f"Low confidence for '{step}': "
            f"best candidate scored {best_confidence:.2f} (below reject threshold 0.50). "
            f"Found {len(candidates)} candidate(s)."
        )
        super().__init__(step=step, message=message, candidates=candidates, screenshot=screenshot)
        self.best_confidence = best_confidence


# ---------------------------------------------------------------------------
# Execution errors (raised by adapter / executor layer)
# ---------------------------------------------------------------------------

class ExecutionFailedError(BubblegumError):
    """
    The adapter raised an exception after the target was successfully resolved.
    The element was found, but the Playwright / Appium action itself failed
    (e.g. element became stale, click intercepted, network error during navigation).
    """


class ValidationFailedError(BubblegumError):
    """
    The action executed but the expected post-action state was not observed.
    Raised by ValidationEngine when the assertion does not pass within the timeout.

    Extra attributes:
        expected — what was expected
        actual   — what was actually observed
    """

    def __init__(
        self,
        step:          str,
        expected:      str | None,
        actual:        str | None,
        resolver_name: str | None = None,
        screenshot:    ArtifactRef | None = None,
    ) -> None:
        message = (
            f"Validation failed for '{step}': "
            f"expected {expected!r}, got {actual!r}."
        )
        super().__init__(
            step=step, message=message,
            resolver_name=resolver_name, screenshot=screenshot,
        )
        self.expected = expected
        self.actual   = actual


# ---------------------------------------------------------------------------
# Context / infrastructure errors
# ---------------------------------------------------------------------------

class ContextCollectionError(BubblegumError):
    """
    The adapter could not capture DOM / hierarchy / screenshot from the current session.
    Typically caused by a crashed browser/app or a disconnected WebDriver session.
    """


class ProviderConfigError(BubblegumError):
    """
    An LLM or vision model provider is not configured or credentials are invalid.
    Raised by the model provider abstraction layer before making any API call.
    """


class AICostPolicyBlockedError(BubblegumError):
    """
    A Tier 3 resolver's cost_level exceeds the configured max_cost_level.
    Raised by the GroundingEngine when max_cost_level=low and Tiers 1+2 both failed.
    The test will not proceed rather than silently spending above the cost policy.
    """


class MemoryStaleError(BubblegumError):
    """
    A cached resolver mapping exists but fails one or more staleness checks:
      - screen signature drift exceeds tolerance
      - element no longer found in DOM/hierarchy
      - element text/role/position drifted beyond threshold
      - mapping has exceeded TTL (default 7 days)
      - failure count for this mapping exceeds max_failures (default 3)

    NOT a hard failure — MemoryCacheResolver returns a lower confidence score
    and allows a downstream resolver to win. This error is raised only when
    the engine decides to surface the staleness explicitly (e.g. in reports).
    """
