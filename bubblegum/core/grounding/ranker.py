"""
bubblegum/core/grounding/ranker.py
====================================
CandidateRanker — applies the weighted confidence formula to a list of ResolvedTarget
candidates and returns them ranked by final score.

Confidence formula weights (from architecture spec):
  text/name match         30%
  role/type match         20%
  visibility/interact.    15%
  uniqueness              15%
  location/proximity      10%
  historical memory       10%

Phase 0 — skeleton. Formula wiring is present; signal extraction is stubbed
and will be filled in during Phase 1/2 when adapters provide real UIContext data.
"""

from __future__ import annotations

import logging

from bubblegum.core.schemas import ResolvedTarget

logger = logging.getLogger(__name__)

# Confidence signal weights — must sum to 1.0
_WEIGHTS: dict[str, float] = {
    "text_match":       0.30,
    "role_match":       0.20,
    "visibility":       0.15,
    "uniqueness":       0.15,
    "proximity":        0.10,
    "memory_history":   0.10,
}


class CandidateRanker:
    """
    Ranks a list of ResolvedTarget candidates by weighted confidence score.

    Usage:
        ranker = CandidateRanker()
        best   = ranker.best(candidates)
        ranked = ranker.rank(candidates)

    Phase 0 note:
        score() reads signal values from target.metadata when available,
        otherwise falls back to the raw confidence already set by the resolver.
        Full signal extraction is implemented in Phase 1+ alongside real UIContext data.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(self, candidates: list[ResolvedTarget]) -> list[ResolvedTarget]:
        """
        Return candidates sorted by final weighted confidence score, descending.
        Non-destructive — returns a new list; input is unchanged.
        """
        if not candidates:
            return []

        scored = [(c, self.score(c)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Return new ResolvedTarget objects with updated confidence scores
        ranked: list[ResolvedTarget] = []
        for target, final_score in scored:
            ranked.append(
                target.model_copy(update={"confidence": round(final_score, 4)})
            )

        logger.debug(
            "Ranked %d candidates. Top: %s (%.2f)",
            len(ranked),
            ranked[0].ref if ranked else "none",
            ranked[0].confidence if ranked else 0.0,
        )
        return ranked

    def best(self, candidates: list[ResolvedTarget]) -> ResolvedTarget:
        """
        Return the single highest-confidence candidate.
        Raises ValueError if candidates is empty (caller must guard).
        """
        if not candidates:
            raise ValueError("Cannot select best from empty candidate list.")
        return self.rank(candidates)[0]

    def score(self, target: ResolvedTarget) -> float:
        """
        Compute the weighted confidence score for a single candidate.

        Phase 0 behaviour:
          Signal values are read from target.metadata["signals"] when present.
          If signals are absent, the resolver's raw confidence is returned unchanged.
          This allows Phase 0 stubs to pass through their own confidence values
          while Phase 1+ resolvers can populate signals for proper weighting.

        Expected metadata structure (Phase 1+):
            target.metadata["signals"] = {
                "text_match":     0.95,
                "role_match":     1.00,
                "visibility":     1.00,
                "uniqueness":     0.80,
                "proximity":      0.70,
                "memory_history": 0.00,
            }
        """
        signals: dict[str, float] | None = target.metadata.get("signals")

        if signals is None:
            # Phase 0 / resolver didn't populate signals — pass through raw confidence
            return target.confidence

        weighted = sum(
            signals.get(signal, 0.0) * weight
            for signal, weight in _WEIGHTS.items()
        )
        return min(max(weighted, 0.0), 1.0)   # clamp to [0, 1]


# ---------------------------------------------------------------------------
# Module-level helpers (used by GroundingEngine and tests)
# ---------------------------------------------------------------------------

def compute_confidence(signals: dict[str, float]) -> float:
    """
    Standalone helper: compute a weighted confidence score from a signals dict.
    Useful for unit-testing signal extraction logic outside of a full resolver run.
    """
    return min(
        max(sum(signals.get(k, 0.0) * w for k, w in _WEIGHTS.items()), 0.0),
        1.0,
    )
