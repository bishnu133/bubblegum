"""Role-aware tie-breaking in the grounding engine.

When two candidates tie on confidence, a click should prefer the interactive
element (e.g. a <button>) over a non-interactive twin (its inner text span).
Genuinely equivalent candidates still raise AmbiguousTargetError. Duplicates of
the same *specific* ref are collapsed; distinct generic refs are not.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import AmbiguousTargetError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent


class _Fixed(Resolver):
    name = "fixed_test"
    priority = 20
    tier = 1
    channels = ["web", "mobile"]

    def __init__(self, candidates):
        self._c = candidates

    def resolve(self, intent):
        return list(self._c)


def _engine(cands):
    reg = ResolverRegistry()
    reg.register(_Fixed(cands))
    return GroundingEngine(registry=reg)


def _t(ref, conf, role=None):
    meta = {"role": role} if role else {}
    return ResolvedTarget(ref=ref, confidence=conf, resolver_name="fixed_test", metadata=meta)


def _intent(action="click"):
    return StepIntent(instruction="Click the X button", channel="web", action_type=action, context={})


def test_button_beats_text_twin_on_tie():
    eng = _engine([
        _t('text="Update account status"', 0.9),                          # inner text, no role
        _t('role=button[name="Update account status"]', 0.9, "button"),   # the button
    ])
    target, _ = asyncio.run(eng.ground(_intent("click")))
    assert target.ref == 'role=button[name="Update account status"]'


def test_two_equivalent_buttons_still_ambiguous():
    eng = _engine([
        _t('role=button[name="A"]', 0.9, "button"),
        _t('role=button[name="B"]', 0.9, "button"),
    ])
    with pytest.raises(AmbiguousTargetError):
        asyncio.run(eng.ground(_intent("click")))


def test_duplicate_specific_ref_is_collapsed():
    # Same specific ref emitted twice must not read as two competing candidates.
    eng = _engine([
        _t('role=button[name="Save"]', 0.9, "button"),
        _t('role=button[name="Save"]', 0.9, "button"),
    ])
    target, _ = asyncio.run(eng.ground(_intent("click")))
    assert target.ref == 'role=button[name="Save"]'
