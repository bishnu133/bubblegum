"""
PR6 — nameless-combobox resolver fallback.

A dropdown/select/combobox trigger with no accessible name (common with MUI /
Angular CDK overlays) scores only 0.60 in the accessibility-tree resolver, which
is below the engine's 0.70 review threshold and would be dropped. When the
instruction signals a dropdown and exactly one nameless combobox is present, it
is lifted into the review band so the step resolves instead of failing.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import LowConfidenceError, ResolutionFailedError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
from bubblegum.core.schemas import StepIntent


def _intent(
    *,
    instruction: str,
    action_type: str,
    snapshot: str,
    target_phrase: str | None = None,
    kind_hint: str | None = None,
) -> StepIntent:
    context: dict = {"a11y_snapshot": snapshot}
    if kind_hint is not None:
        context["relational_intent"] = {"control_kind_hint": kind_hint}
    return StepIntent(
        instruction=instruction,
        channel="web",
        action_type=action_type,
        target_phrase=target_phrase,
        context=context,
    )


# ---------------------------------------------------------------------------
# Resolver-level behaviour
# ---------------------------------------------------------------------------

def test_resolver_promotes_unique_nameless_combobox_with_kind_hint():
    resolver = AccessibilityTreeResolver()
    intent = _intent(
        instruction="Open the country dropdown",
        action_type="click",
        target_phrase="country dropdown",
        snapshot="- combobox",
        kind_hint="dropdown",
    )
    cands = resolver.resolve(intent)
    combo = [c for c in cands if c.ref == "role=combobox"]
    assert combo, "nameless combobox produced no candidate"
    assert combo[0].confidence >= 0.70
    assert combo[0].metadata.get("nameless_combobox_fallback") is True


def test_resolver_promotes_on_select_action_without_kind_hint():
    resolver = AccessibilityTreeResolver()
    intent = _intent(
        instruction="Select India",
        action_type="select",
        snapshot="- combobox",
    )
    combo = [c for c in resolver.resolve(intent) if c.ref == "role=combobox"]
    assert combo and combo[0].confidence >= 0.70


def test_resolver_does_not_promote_without_dropdown_intent():
    # action=click, no dropdown kind hint → a bare combobox stays at its low
    # base score and is not promoted (we don't grab arbitrary nameless widgets).
    resolver = AccessibilityTreeResolver()
    intent = _intent(
        instruction="Click submit",
        action_type="click",
        target_phrase="submit",
        snapshot="- combobox",
    )
    combo = [c for c in resolver.resolve(intent) if c.ref == "role=combobox"]
    assert combo, "candidate should still exist (role fits click)"
    assert combo[0].metadata.get("nameless_combobox_fallback") is not True
    assert combo[0].confidence < 0.70


def test_resolver_does_not_promote_when_multiple_nameless_comboboxes():
    resolver = AccessibilityTreeResolver()
    intent = _intent(
        instruction="Open the dropdown",
        action_type="select",
        snapshot="- combobox\n- combobox",
    )
    combo = [c for c in resolver.resolve(intent) if c.ref == "role=combobox"]
    assert all(c.metadata.get("nameless_combobox_fallback") is not True for c in combo)


def test_named_combobox_still_preferred_over_nameless_fallback():
    # A named combobox matching the phrase must outrank the nameless fallback.
    resolver = AccessibilityTreeResolver()
    intent = _intent(
        instruction="Select India from Country",
        action_type="select",
        target_phrase="Country",
        snapshot='- combobox "Country"\n- combobox',
        kind_hint="dropdown",
    )
    cands = sorted(resolver.resolve(intent), key=lambda c: -c.confidence)
    assert cands[0].ref == 'role=combobox[name="Country"]'


# ---------------------------------------------------------------------------
# End-to-end through the grounding engine
# ---------------------------------------------------------------------------

def test_engine_resolves_nameless_combobox():
    engine = GroundingEngine(registry=ResolverRegistry())
    intent = _intent(
        instruction="Open the country dropdown",
        action_type="click",
        target_phrase="country dropdown",
        snapshot="- combobox",
        kind_hint="dropdown",
    )
    target, _ = asyncio.run(engine.ground(intent))
    assert target.ref == "role=combobox"
    assert target.metadata.get("nameless_combobox_fallback") is True


def test_engine_fails_on_ambiguous_nameless_comboboxes():
    engine = GroundingEngine(registry=ResolverRegistry())
    intent = _intent(
        instruction="Open the dropdown",
        action_type="select",
        snapshot="- combobox\n- combobox",
    )
    with pytest.raises((LowConfidenceError, ResolutionFailedError)):
        asyncio.run(engine.ground(intent))
