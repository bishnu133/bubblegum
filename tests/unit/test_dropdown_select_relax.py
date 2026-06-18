"""Dropdown/select confidence relax in the grounding engine.

A custom combobox (Ant Design / MUI / CDK) has no useful accessible name, so a
"select X from the Y dropdown" step scores only role-fit confidence (~0.57),
below the 0.70 review bar. For a dropdown/select intent the engine accepts the
best combobox/listbox candidate above the reject threshold instead of raising
LowConfidenceError — but only for dropdown intents, and still guarded by the
ambiguity check.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import LowConfidenceError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent


class _FixedResolver(Resolver):
    """Returns pre-baked candidates regardless of intent (tier 2, fuzzy)."""

    name = "fixed_test"
    priority = 45
    tier = 2
    channels = ["web", "mobile"]

    def __init__(self, candidates):
        self._candidates = candidates

    def resolve(self, intent):
        return list(self._candidates)


def _engine(candidates):
    reg = ResolverRegistry()
    reg.register(_FixedResolver(candidates))
    return GroundingEngine(registry=reg)


def _combo(ref, conf):
    return ResolvedTarget(ref=ref, confidence=conf, resolver_name="fixed_test",
                          metadata={"role": "combobox"})


def _intent(instruction, action_type, target_phrase=None):
    return StepIntent(instruction=instruction, channel="web",
                      action_type=action_type, target_phrase=target_phrase, context={})


def test_select_accepts_low_confidence_combobox():
    eng = _engine([_combo("role=combobox", 0.57)])
    intent = _intent("Select Participant from the search type dropdown", "select", "search type")
    target, _ = asyncio.run(eng.ground(intent))
    assert target.ref == "role=combobox"
    assert target.confidence == pytest.approx(0.57)


def test_dropdown_keyword_click_accepts_combobox():
    eng = _engine([_combo("role=combobox", 0.6)])
    intent = _intent("Open the search type dropdown", "click", "search type")
    target, _ = asyncio.run(eng.ground(intent))
    assert target.ref == "role=combobox"


def test_non_dropdown_click_still_rejects_low_confidence():
    # Same low-confidence combobox, but a plain click with no dropdown signal
    # must NOT be relaxed — the review bar still applies.
    eng = _engine([_combo("role=combobox", 0.57)])
    intent = _intent("Click the thing", "click", "thing")
    with pytest.raises(LowConfidenceError):
        asyncio.run(eng.ground(intent))


def test_below_reject_threshold_is_not_accepted():
    eng = _engine([_combo("role=combobox", 0.40)])
    intent = _intent("Select X from the Y dropdown", "select", "Y")
    with pytest.raises(LowConfidenceError):
        asyncio.run(eng.ground(intent))


def test_multiple_distinct_comboboxes_not_relaxed():
    # Two different comboboxes: the relax only fires for a single combobox, so
    # this stays a low-confidence failure rather than silently picking one.
    eng = _engine([_combo("role=combobox", 0.57), _combo("role=combobox[name=\"b\"]", 0.57)])
    intent = _intent("Select X from the Y dropdown", "select", "Y")
    with pytest.raises(LowConfidenceError):
        asyncio.run(eng.ground(intent))


def test_named_combobox_relaxed_even_if_found_twice():
    # A named combobox found by two resolvers (same ref) is still uniquely
    # identifiable, so it resolves.
    named = lambda c: ResolvedTarget(ref='role=combobox[name="Participant"]', confidence=c,
                                     resolver_name="fixed_test",
                                     metadata={"role": "combobox", "name": "Participant"})
    eng = _engine([named(0.57), named(0.55)])
    intent = _intent("Select Participant from the search type dropdown", "select", "search type")
    target, _ = asyncio.run(eng.ground(intent))
    assert target.ref == 'role=combobox[name="Participant"]'


def test_non_combobox_low_confidence_select_still_rejects():
    # A select intent whose only candidate is not a combobox is not relaxed.
    tgt = ResolvedTarget(ref="text=Search", confidence=0.57, resolver_name="fixed_test",
                         metadata={"role": "button"})
    eng = _engine([tgt])
    intent = _intent("Select X from the Y dropdown", "select", "Y")
    with pytest.raises(LowConfidenceError):
        asyncio.run(eng.ground(intent))
