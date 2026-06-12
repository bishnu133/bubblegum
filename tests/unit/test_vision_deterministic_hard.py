"""Validate that the AI (vision) tier wins on a deterministic-hard target.

On real pages the deterministic tiers win because elements have clean
accessible names. This module constructs the opposite: an icon/image control
with **no** accessible name that no text/role resolver can match, and proves the
vision tier is what resolves it — and, by contrast, that vision does NOT
displace a clean deterministic match, and that without vision candidates the
deterministic-hard target fails to resolve at all.

No network / API key required: vision candidates are injected exactly as the
screenshot→provider pipeline would inject them (intent.context["vision_candidates"]).
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.errors import BubblegumError
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import ExecutionOptions, StepIntent
from bubblegum.core.vision.engine import VisionCandidate


def _engine() -> GroundingEngine:
    return GroundingEngine(registry=ResolverRegistry())


# An accessibility snapshot for a toolbar of icon-only buttons: the buttons
# carry NO accessible name, so exact/fuzzy/a11y text matching cannot resolve
# "the settings icon".
_NAMELESS_ICON_SNAPSHOT = "\n".join([
    "- banner:",
    "  - img",
    "- navigation:",
    "  - button",
    "  - button",
    "  - button",
    "- main:",
    '  - heading "Dashboard"',
])


def _intent(*, vision_candidates=None, cost: str = "high", snapshot: str = _NAMELESS_ICON_SNAPSHOT) -> StepIntent:
    context = {"a11y_snapshot": snapshot}
    if vision_candidates is not None:
        context["vision_candidates"] = vision_candidates
        context["config_vision_enabled"] = True
    return StepIntent(
        instruction="Click the settings icon",
        channel="web",
        platform="web",
        action_type="click",
        target_phrase="settings icon",
        context=context,
        options=ExecutionOptions(max_cost_level=cost),
    )


def _settings_candidate() -> VisionCandidate:
    # What a vision model returns after recognising the cog glyph.
    return VisionCandidate(
        label="settings icon",
        text="settings",
        role="button",
        bbox=[120, 16, 152, 48],
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# Vision wins when deterministic tiers cannot
# ---------------------------------------------------------------------------


def test_vision_tier_wins_on_nameless_icon_target():
    intent = _intent(vision_candidates=[_settings_candidate()])
    target, traces = asyncio.run(_engine().ground(intent))

    assert target.resolver_name == "vision_model"
    assert target.confidence >= 0.70
    assert target.metadata.get("source") == "vision"
    # The deterministic resolvers were tried first and did run.
    assert {t.resolver_name for t in traces} >= {"accessibility_tree", "exact_text"}


def test_deterministic_hard_target_fails_without_vision_candidates():
    # Same nameless snapshot, no vision candidates injected → nothing resolves.
    intent = _intent(vision_candidates=None)
    with pytest.raises(BubblegumError):
        asyncio.run(_engine().ground(intent))


# ---------------------------------------------------------------------------
# Vision does NOT displace a clean deterministic match
# ---------------------------------------------------------------------------


def test_deterministic_wins_when_target_has_a_clean_name():
    named_snapshot = "\n".join([
        "- navigation:",
        '  - button "Settings"',
        '  - button "Profile"',
        '- heading "Dashboard"',
    ])
    intent = _intent(
        vision_candidates=[_settings_candidate()],
        snapshot=named_snapshot,
    )
    # Instruction names the control directly so the a11y tier matches cleanly.
    intent.instruction = "Click Settings"
    intent.target_phrase = "Settings"

    target, _ = asyncio.run(_engine().ground(intent))

    # A non-AI tier resolves it; the high-cost vision tier never needs to win.
    assert target.resolver_name != "vision_model"
    assert target.ref in {'role=button[name="Settings"]', 'text="Settings"'}


def test_vision_tier_blocked_under_low_cost_policy():
    # cost=low disables the high-cost vision resolver entirely; the
    # deterministic-hard target then surfaces a cost-policy block.
    intent = _intent(vision_candidates=[_settings_candidate()], cost="low")
    with pytest.raises(BubblegumError):
        asyncio.run(_engine().ground(intent))
