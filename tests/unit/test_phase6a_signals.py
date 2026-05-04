from bubblegum.core.grounding.signals import clamp_signal, make_signals
from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.schemas import ResolvedTarget


def test_clamp_signal_bounds():
    assert clamp_signal(-1) == 0.0
    assert clamp_signal(2) == 1.0
    assert clamp_signal(0.42) == 0.42


def test_make_signals_emits_memory_aliases():
    s = make_signals(text_match=1.2, memory=0.7)
    assert s["text_match"] == 1.0
    assert s["memory"] == 0.7
    assert s["memory_history"] == 0.7


def test_ranker_memory_alias_equivalence():
    ranker = CandidateRanker()
    t1 = ResolvedTarget(ref="a", confidence=0.1, resolver_name="x", metadata={"signals": make_signals(memory=0.8)})
    t2 = ResolvedTarget(ref="b", confidence=0.1, resolver_name="x", metadata={"signals": make_signals(memory_history=0.8)})
    assert ranker.score(t1) == ranker.score(t2)
