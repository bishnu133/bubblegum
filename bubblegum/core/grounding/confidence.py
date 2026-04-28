"""
bubblegum/core/grounding/confidence.py
========================================
Threshold constants and helper functions for confidence evaluation.

These values are the defaults defined in the architecture spec.
At runtime, BubblegumConfig overrides them from bubblegum.yaml.

Phase 0 — constants and threshold check helpers only.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Default thresholds (all configurable via bubblegum.yaml)
# ---------------------------------------------------------------------------

ACCEPT_THRESHOLD:  float = 0.85  # Tier 1/2: stop immediately — high confidence
REVIEW_THRESHOLD:  float = 0.70  # Tier 2:   proceed but log a warning
AMBIGUOUS_GAP:     float = 0.05  # Top 2 candidates too close — raise AmbiguousTargetError
REJECT_THRESHOLD:  float = 0.50  # Below this: continue to next tier / raise error


# ---------------------------------------------------------------------------
# Threshold predicates
# ---------------------------------------------------------------------------

def is_accepted(confidence: float, threshold: float = ACCEPT_THRESHOLD) -> bool:
    """True if confidence is high enough to stop resolution immediately."""
    return confidence >= threshold


def is_reviewable(confidence: float, threshold: float = REVIEW_THRESHOLD) -> bool:
    """True if confidence is acceptable but warrants a warning in the trace."""
    return confidence >= threshold


def is_ambiguous(gap: float, threshold: float = AMBIGUOUS_GAP) -> bool:
    """True if the confidence gap between top 2 candidates is too narrow to auto-execute."""
    return gap < threshold


def is_rejected(confidence: float, threshold: float = REJECT_THRESHOLD) -> bool:
    """True if confidence is too low to trust — should try next tier or raise."""
    return confidence < threshold
