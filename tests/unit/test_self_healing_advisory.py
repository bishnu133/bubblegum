"""
Self-healing defect advisory (PR2).

When act() resolves a step via a fuzzy/synonym match that substitutes a
different element label than the tester wrote, Bubblegum should:
  - mark the step "recovered" (not silently "passed") for meaningful drift,
  - attach a `healing` advisory to the target metadata,
  - surface it in the HTML and JSON reports.

Exact / clean matches must keep status "passed" and carry no advisory.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from bubblegum.core import sdk
from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
from bubblegum.core.sdk import _build_healing_advisory
from bubblegum.core.schemas import (
    ArtifactRef,
    ExecutionResult,
    ResolvedTarget,
    StepIntent,
    StepResult,
    UIContext,
    ValidationResult,
)
from bubblegum.reporting.html_report import build_report_analytics, write_html_report
from bubblegum.reporting.json_report import write_json_report


def _intent(target_phrase: str, instruction: str = "Click login") -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel="web",
        action_type="click",
        target_phrase=target_phrase,
    )


def _fuzzy_target(element_name: str, fuzzy_ratio: float = 0.78) -> ResolvedTarget:
    return ResolvedTarget(
        ref=f'role=button[name="{element_name}"]',
        confidence=0.78,
        resolver_name="fuzzy_text",
        metadata={"element_name": element_name, "fuzzy_ratio": fuzzy_ratio},
    )


# ---------------------------------------------------------------------------
# _build_healing_advisory
# ---------------------------------------------------------------------------

class TestHealingAdvisory:
    def test_synonym_substitution_flagged_for_review(self):
        advisory = _build_healing_advisory(_intent("login"), _fuzzy_target("Sign In"))
        assert advisory is not None
        assert advisory["applied"] is True
        assert advisory["severity"] == "review"
        assert advisory["match_kind"] == "synonym"
        assert advisory["requested"] == "login"
        assert advisory["matched"] == "Sign In"
        assert "revisit your test step" in advisory["message"].lower()

    def test_benign_typo_is_info_not_review(self):
        # "Logut" vs "Logout" — near-identical, a typo-level correction.
        advisory = _build_healing_advisory(_intent("Logut"), _fuzzy_target("Logout"))
        assert advisory is not None
        assert advisory["severity"] == "info"
        assert advisory["match_kind"] == "fuzzy"

    def test_exact_match_returns_none(self):
        advisory = _build_healing_advisory(_intent("Login"), _fuzzy_target("Login"))
        assert advisory is None

    def test_substring_containment_returns_none(self):
        advisory = _build_healing_advisory(
            _intent("Continue"), _fuzzy_target("Continue to checkout")
        )
        assert advisory is None

    def test_non_fuzzy_resolver_returns_none(self):
        target = ResolvedTarget(
            ref='role=button[name="Sign In"]',
            confidence=0.96,
            resolver_name="accessibility_tree",
            metadata={"element_name": "Sign In"},
        )
        assert _build_healing_advisory(_intent("login"), target) is None


# ---------------------------------------------------------------------------
# _resolve_healing_advisory — live heal + cache replay
# ---------------------------------------------------------------------------

class TestResolveHealingAdvisory:
    def test_delegates_to_live_fuzzy_heal(self):
        advisory = sdk._resolve_healing_advisory(_intent("login"), _fuzzy_target("Sign In"))
        assert advisory is not None
        assert advisory["matched"] == "Sign In"
        # A live heal is not tagged as a replay.
        assert "replayed_from_cache" not in advisory

    def test_resurfaces_persisted_advisory_on_cache_replay(self):
        cached_target = ResolvedTarget(
            ref='role=button[name="Sign In"]',
            confidence=0.78,
            resolver_name="memory_cache",
            metadata={
                "healing": {
                    "applied": True,
                    "requested": "login",
                    "matched": "Sign In",
                    "severity": "review",
                    "match_kind": "synonym",
                }
            },
        )
        advisory = sdk._resolve_healing_advisory(_intent("login"), cached_target)
        assert advisory is not None
        assert advisory["replayed_from_cache"] is True
        assert advisory["severity"] == "review"
        assert advisory["matched"] == "Sign In"

    def test_cache_hit_without_healing_returns_none(self):
        clean_cached = ResolvedTarget(
            ref='role=button[name="Login"]',
            confidence=0.96,
            resolver_name="memory_cache",
            metadata={"element_name": "Login"},
        )
        assert sdk._resolve_healing_advisory(_intent("Login"), clean_cached) is None


# ---------------------------------------------------------------------------
# act() status wiring
# ---------------------------------------------------------------------------

class _FakeAdapter:
    """Resolves every step to a synonym-healed 'Sign In' button via fuzzy_text."""

    def __init__(self, snapshot: str):
        self._snapshot = snapshot
        # Unique signature per instance so the persistent memory-cache resolver
        # never returns a stale hit that would shadow fuzzy_text resolution.
        self._sig = f"sig-{uuid.uuid4()}"

    async def collect_context(self, _request):
        return UIContext(a11y_snapshot=self._snapshot, screen_signature=self._sig)

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png")


@pytest.fixture
def _isolated_memory(tmp_path, monkeypatch):
    """Point act()'s shared memory cache at a throwaway DB so the persistent
    .bubblegum/memory.db does not let a cached resolution shadow fuzzy_text."""
    monkeypatch.setattr(
        sdk, "_memory_cache", MemoryCacheResolver(db_path=tmp_path / "mem.db")
    )


def test_act_marks_synonym_heal_as_recovered(_isolated_memory, monkeypatch):
    adapter = _FakeAdapter('- button "Sign In"')
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = asyncio.run(sdk.act("Click login", channel="web", page=object()))

    assert result.status == "recovered"
    assert result.target is not None
    healing = result.target.metadata.get("healing")
    assert healing is not None
    assert healing["severity"] == "review"
    assert healing["matched"] == "Sign In"


def test_act_keeps_exact_match_passed(_isolated_memory, monkeypatch):
    adapter = _FakeAdapter('- button "Login"')
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = asyncio.run(sdk.act("Click Login", channel="web", page=object()))

    assert result.status == "passed"
    assert "healing" not in (result.target.metadata if result.target else {})


# ---------------------------------------------------------------------------
# Healing advisory survives a memory-cache replay
# ---------------------------------------------------------------------------

@pytest.fixture
def _shared_isolated_memory(tmp_path, monkeypatch):
    """Point BOTH the SDK write-side cache and the registry read-side resolver
    at one throwaway DB, so a second act() of the same step replays from it."""
    res = MemoryCacheResolver(db_path=tmp_path / "mem.db")
    monkeypatch.setattr(sdk, "_memory_cache", res)
    original = sdk._registry.get("memory_cache")
    sdk._registry.register(res)  # replaces the built-in by name
    try:
        yield res
    finally:
        if original is not None:
            sdk._registry.register(original)


def test_healing_advisory_is_persisted_and_replays_from_cache(_shared_isolated_memory, monkeypatch):
    res = _shared_isolated_memory
    adapter = _FakeAdapter('- button "Sign In"')
    adapter._sig = "sig-replay"  # fixed signature → stable cache key across runs
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    # First run: synonym heal, marked recovered and persisted to the cache.
    first = asyncio.run(sdk.act("Click login", channel="web", page=object()))
    assert first.status == "recovered"
    assert first.target.metadata["healing"]["matched"] == "Sign In"

    # The advisory was written into the cached metadata (the core of the fix):
    # a direct cache lookup of the same step returns it.
    lookup = _intent("login", instruction="Click login")
    lookup.context["screen_signature"] = "sig-replay"
    cached = res.resolve(lookup)
    assert cached, "expected a memory-cache hit on replay"
    assert cached[0].resolver_name == "memory_cache"
    assert cached[0].metadata.get("healing", {}).get("matched") == "Sign In"

    # Re-surfacing tags it as a replay.
    replayed = sdk._resolve_healing_advisory(lookup, cached[0])
    assert replayed is not None
    assert replayed["replayed_from_cache"] is True

    # End-to-end invariant: the replayed step stays "recovered", never silently
    # downgraded to "passed", and still carries the advisory.
    second = asyncio.run(sdk.act("Click login", channel="web", page=object()))
    assert second.status == "recovered"
    assert second.target.metadata.get("healing") is not None


# ---------------------------------------------------------------------------
# Report surfacing
# ---------------------------------------------------------------------------

def _healed_result(severity: str = "review") -> StepResult:
    return StepResult(
        status="recovered" if severity == "review" else "passed",
        action="Click login",
        confidence=0.78,
        target=ResolvedTarget(
            ref='role=button[name="Sign In"]',
            confidence=0.78,
            resolver_name="fuzzy_text",
            metadata={
                "element_name": "Sign In",
                "healing": {
                    "applied": True,
                    "requested": "login",
                    "matched": "Sign In",
                    "resolver": "fuzzy_text",
                    "match_kind": "synonym",
                    "similarity": 0.78,
                    "severity": severity,
                    "message": "Self-healing applied: ... please revisit your test step.",
                },
            },
        ),
    )


def test_analytics_counts_healed_steps():
    analytics = build_report_analytics([_healed_result(), _healed_result("info")])
    summary = analytics["healing_summary"]
    assert summary["total"] == 2
    assert summary["severity_counts"]["review"] == 1
    assert summary["severity_counts"]["info"] == 1
    assert summary["match_kind_counts"]["synonym"] == 2


def test_html_report_shows_healing_banner_and_callout(tmp_path):
    out = write_html_report([_healed_result()], path=tmp_path / "report.html")
    text = out.read_text(encoding="utf-8")
    assert "Self-healing was applied to 1 step" in text
    assert "possible defect" in text
    assert "Sign In" in text
    assert "login" in text


def test_html_report_no_healing_banner_when_clean(tmp_path):
    clean = StepResult(status="passed", action="Click", confidence=0.96)
    out = write_html_report([clean], path=tmp_path / "report.html")
    assert "Self-healing was applied" not in out.read_text(encoding="utf-8")


def test_html_report_escapes_healing_values(tmp_path):
    result = _healed_result()
    result.target.metadata["healing"]["matched"] = "<script>alert(1)</script>"
    out = write_html_report([result], path=tmp_path / "report.html")
    text = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text


def test_json_report_includes_healing(tmp_path):
    out = write_json_report([_healed_result()], path=tmp_path / "report.json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    healing = payload["results"][0]["target"]["metadata"]["healing"]
    assert healing["severity"] == "review"
    assert healing["matched"] == "Sign In"
    assert payload["analytics"]["healing_summary"]["total"] == 1
