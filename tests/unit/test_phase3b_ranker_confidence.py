from __future__ import annotations

from bubblegum.core.grounding.ranker import CandidateRanker, compute_confidence
from bubblegum.core.schemas import ResolvedTarget


def _t(ref: str, confidence: float = 0.5, signals: dict | None = None) -> ResolvedTarget:
    metadata = {}
    if signals is not None:
        metadata["signals"] = signals
    return ResolvedTarget(ref=ref, confidence=confidence, resolver_name="test", metadata=metadata)


def test_compute_confidence_clamps_above_one():
    signals = {
        "text_match": 5.0,
        "role_match": 5.0,
        "visibility": 5.0,
        "uniqueness": 5.0,
        "proximity": 5.0,
        "memory_history": 5.0,
    }
    assert compute_confidence(signals) == 1.0


def test_compute_confidence_clamps_below_zero():
    signals = {
        "text_match": -5.0,
        "role_match": -5.0,
        "visibility": -5.0,
        "uniqueness": -5.0,
        "proximity": -5.0,
        "memory_history": -5.0,
    }
    assert compute_confidence(signals) == 0.0


def test_missing_signal_keys_default_to_zero_weighted_value():
    # Only one signal present; others should be treated as 0.
    score = compute_confidence({"text_match": 1.0})
    assert score == 0.30


def test_rank_order_is_deterministic_for_tied_scores():
    ranker = CandidateRanker()
    # Python sort is stable; tied keys preserve input order.
    a = _t("a", signals={"text_match": 1.0})
    b = _t("b", signals={"text_match": 1.0})
    ranked = ranker.rank([a, b])
    assert [r.ref for r in ranked] == ["a", "b"]


def test_best_returns_clear_winner():
    ranker = CandidateRanker()
    low = _t("low", signals={"text_match": 0.1})
    high = _t("high", signals={"text_match": 1.0, "role_match": 1.0, "visibility": 1.0})
    assert ranker.best([low, high]).ref == "high"


def test_score_passthrough_when_signals_absent():
    ranker = CandidateRanker()
    target = _t("x", confidence=0.77, signals=None)
    assert ranker.score(target) == 0.77
