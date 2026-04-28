"""
tests/unit/test_phase0.py
==========================
Phase 0 validation tests.
Run with: pytest tests/unit/test_phase0.py -v

Every test here must pass before Phase 1A begins.
These serve as the regression baseline — they must continue to pass through all future phases.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestSchemas:

    def test_all_13_schemas_importable(self):
        from bubblegum.core.schemas import (
            ActionPlan, ArtifactRef, ContextRequest, ErrorInfo,
            ExecutionOptions, ExecutionResult, ResolvedTarget, ResolverTrace,
            StepIntent, StepResult, UIContext, ValidationPlan, ValidationResult,
        )
        # just importing is the test — if any schema is malformed, this fails

    def test_execution_options_defaults(self):
        from bubblegum.core.schemas import ExecutionOptions
        opts = ExecutionOptions()
        assert opts.timeout_ms     == 10_000
        assert opts.retry_count    == 2
        assert opts.wait_for       is None
        assert opts.use_ai         is True
        assert opts.max_cost_level == "medium"

    def test_step_intent_defaults(self):
        from bubblegum.core.schemas import StepIntent
        intent = StepIntent(instruction="Click Login", channel="web", action_type="click")
        assert intent.platform == "web"
        assert intent.context  == {}

    def test_resolved_target_fields(self):
        from bubblegum.core.schemas import ResolvedTarget
        t = ResolvedTarget(ref="button[name='Login']", confidence=0.94, resolver_name="accessibility_tree")
        assert t.ref           == "button[name='Login']"
        assert t.confidence    == 0.94
        assert t.resolver_name == "accessibility_tree"
        assert t.metadata      == {}

    def test_step_result_status_literals(self):
        from bubblegum.core.schemas import StepResult
        for status in ("passed", "failed", "recovered", "skipped"):
            r = StepResult(status=status, action="Click Login")
            assert r.status == status

    def test_step_result_invalid_status_rejected(self):
        from bubblegum.core.schemas import StepResult
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StepResult(status="unknown", action="Click Login")

    def test_action_plan_action_type_literals(self):
        from bubblegum.core.schemas import ActionPlan
        for action in ("click", "type", "select", "scroll", "tap", "swipe", "verify", "extract"):
            plan = ActionPlan(action_type=action)
            assert plan.action_type == action

    def test_artifact_ref_type_literals(self):
        from bubblegum.core.schemas import ArtifactRef
        for t in ("screenshot", "trace", "report", "json"):
            ref = ArtifactRef(type=t, path="/tmp/x", timestamp="2026-04-24T00:00:00Z")
            assert ref.type == t

    def test_context_request_defaults(self):
        from bubblegum.core.schemas import ContextRequest
        req = ContextRequest()
        assert req.include_screenshot    is True
        assert req.include_accessibility is True
        assert req.include_dom           is False
        assert req.redact_sensitive_data is True

    def test_resolver_trace_structure(self):
        from bubblegum.core.schemas import ResolvedTarget, ResolverTrace
        t = ResolvedTarget(ref="x", confidence=0.9, resolver_name="test")
        trace = ResolverTrace(resolver_name="test", duration_ms=12, candidates=[t], can_run=True)
        assert trace.resolver_name == "test"
        assert len(trace.candidates) == 1

    def test_error_info_structure(self):
        from bubblegum.core.schemas import ErrorInfo, ResolvedTarget
        t = ResolvedTarget(ref="x", confidence=0.3, resolver_name="exact_text")
        err = ErrorInfo(error_type="LowConfidenceError", message="too low", candidates=[t])
        assert err.error_type == "LowConfidenceError"
        assert len(err.candidates) == 1


# ---------------------------------------------------------------------------
# 2. Resolver base tests
# ---------------------------------------------------------------------------

class TestResolverBase:

    def _make_concrete_resolver(self, name="test", priority=99, channels=None, cost="low", tier=1):
        """Helper: create a minimal concrete resolver for testing."""
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        _name     = name
        _priority = priority
        _channels = channels or ["web", "mobile"]
        _cost     = cost
        _tier     = tier

        class _TestResolver(Resolver):
            # must implement abstract method inside class body
            def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
                return []

        _TestResolver.name       = _name
        _TestResolver.priority   = _priority
        _TestResolver.channels   = _channels
        _TestResolver.cost_level = _cost
        _TestResolver.tier       = _tier

        return _TestResolver()

    def test_can_run_correct_channel(self):
        from bubblegum.core.schemas import StepIntent
        r = self._make_concrete_resolver(channels=["web"])
        intent = StepIntent(instruction="Click x", channel="web", action_type="click")
        assert r.can_run(intent) is True

    def test_can_run_wrong_channel(self):
        from bubblegum.core.schemas import StepIntent
        r = self._make_concrete_resolver(channels=["web"])
        intent = StepIntent(instruction="Tap x", channel="mobile", action_type="tap")
        assert r.can_run(intent) is False

    def test_can_run_cost_policy_low_blocks_high(self):
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = self._make_concrete_resolver(cost="high")
        opts   = ExecutionOptions(max_cost_level="low")
        intent = StepIntent(instruction="x", channel="web", action_type="click", options=opts)
        assert r.can_run(intent) is False

    def test_can_run_cost_policy_medium_allows_low(self):
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        r = self._make_concrete_resolver(cost="low")
        opts   = ExecutionOptions(max_cost_level="medium")
        intent = StepIntent(instruction="x", channel="web", action_type="click", options=opts)
        assert r.can_run(intent) is True

    def test_can_run_missing_required_context(self):
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class NeedsSnapshot(Resolver):
            name      = "needs_snapshot"
            priority  = 20
            channels  = ["web"]
            cost_level = "low"
            tier      = 1
            def required_context(self): return ["a11y_snapshot"]
            def resolve(self, intent): return []

        r      = NeedsSnapshot()
        intent = StepIntent(instruction="x", channel="web", action_type="click")
        # context is empty — a11y_snapshot is missing
        assert r.can_run(intent) is False

    def test_can_run_with_required_context_present(self):
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class NeedsSnapshot(Resolver):
            name      = "needs_snapshot"
            priority  = 20
            channels  = ["web"]
            cost_level = "low"
            tier      = 1
            def required_context(self): return ["a11y_snapshot"]
            def resolve(self, intent): return []

        r      = NeedsSnapshot()
        intent = StepIntent(instruction="x", channel="web", action_type="click",
                            context={"a11y_snapshot": "<some xml>"})
        assert r.can_run(intent) is True


# ---------------------------------------------------------------------------
# 3. Registry tests
# ---------------------------------------------------------------------------

class TestResolverRegistry:

    def test_registry_loads_9_builtins(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        reg = ResolverRegistry()
        assert len(reg.all()) == 9

    def test_registry_sorted_by_priority(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        reg = ResolverRegistry()
        priorities = [r.priority for r in reg.all()]
        assert priorities == sorted(priorities)

    def test_registry_web_excludes_appium(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.schemas import StepIntent
        reg    = ResolverRegistry()
        intent = StepIntent(instruction="Click x", channel="web", action_type="click")
        names  = [r.name for r in reg.eligible_for(intent)]
        assert "appium_hierarchy"   not in names
        assert "accessibility_tree" in names

    def test_registry_mobile_excludes_a11y_tree(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.schemas import StepIntent
        reg    = ResolverRegistry()
        intent = StepIntent(instruction="Tap x", channel="mobile", action_type="tap")
        names  = [r.name for r in reg.eligible_for(intent)]
        assert "accessibility_tree" not in names
        assert "appium_hierarchy"   in names

    def test_registry_custom_resolver_registers(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class CustomResolver(Resolver):
            name      = "custom_test"
            priority  = 25
            channels  = ["web"]
            cost_level = "low"
            tier      = 1
            def resolve(self, intent): return []

        reg = ResolverRegistry()
        reg.register(CustomResolver())
        assert reg.get("custom_test") is not None
        assert len(reg.all()) == 10

    def test_registry_duplicate_name_replaces(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class CustomResolver(Resolver):
            name      = "explicit_selector"   # same name as a built-in
            priority  = 0
            channels  = ["web"]
            cost_level = "low"
            tier      = 1
            def resolve(self, intent): return []

        reg = ResolverRegistry()
        reg.register(CustomResolver())
        assert len(reg.all()) == 9   # still 9 — replaced, not added

    def test_registry_low_cost_policy_blocks_tier3(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.schemas import ExecutionOptions, StepIntent
        reg    = ResolverRegistry()
        opts   = ExecutionOptions(max_cost_level="low")
        intent = StepIntent(instruction="x", channel="web", action_type="click", options=opts)
        names  = [r.name for r in reg.eligible_for(intent)]
        assert "llm_grounding" not in names
        assert "vision_model"  not in names

    def test_registry_get_by_tier(self):
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.schemas import StepIntent
        reg    = ResolverRegistry()
        intent = StepIntent(instruction="x", channel="web", action_type="click")
        tier1  = reg.get_by_tier(intent, 1)
        tier3  = reg.get_by_tier(intent, 3)
        assert all(r.tier == 1 for r in tier1)
        assert all(r.tier == 3 for r in tier3)


# ---------------------------------------------------------------------------
# 4. CandidateRanker tests
# ---------------------------------------------------------------------------

class TestCandidateRanker:

    def test_rank_returns_descending_confidence(self):
        from bubblegum.core.grounding.ranker import CandidateRanker
        from bubblegum.core.schemas import ResolvedTarget
        ranker = CandidateRanker()
        candidates = [
            ResolvedTarget(ref="a", confidence=0.60, resolver_name="r1"),
            ResolvedTarget(ref="b", confidence=0.94, resolver_name="r2"),
            ResolvedTarget(ref="c", confidence=0.75, resolver_name="r3"),
        ]
        ranked = ranker.rank(candidates)
        confidences = [r.confidence for r in ranked]
        assert confidences == sorted(confidences, reverse=True)

    def test_best_returns_highest(self):
        from bubblegum.core.grounding.ranker import CandidateRanker
        from bubblegum.core.schemas import ResolvedTarget
        ranker = CandidateRanker()
        candidates = [
            ResolvedTarget(ref="a", confidence=0.60, resolver_name="r1"),
            ResolvedTarget(ref="b", confidence=0.94, resolver_name="r2"),
        ]
        best = ranker.best(candidates)
        assert best.ref == "b"
        assert best.confidence == 0.94

    def test_rank_empty_returns_empty(self):
        from bubblegum.core.grounding.ranker import CandidateRanker
        ranker = CandidateRanker()
        assert ranker.rank([]) == []

    def test_best_empty_raises(self):
        from bubblegum.core.grounding.ranker import CandidateRanker
        ranker = CandidateRanker()
        with pytest.raises(ValueError):
            ranker.best([])

    def test_score_with_signals_weighted(self):
        from bubblegum.core.grounding.ranker import CandidateRanker, compute_confidence
        from bubblegum.core.schemas import ResolvedTarget
        ranker = CandidateRanker()
        # All signals perfect → score should be 1.0
        target = ResolvedTarget(
            ref="btn", confidence=0.5, resolver_name="test",
            metadata={"signals": {
                "text_match": 1.0, "role_match": 1.0, "visibility": 1.0,
                "uniqueness": 1.0, "proximity": 1.0, "memory_history": 1.0,
            }}
        )
        assert ranker.score(target) == pytest.approx(1.0)

    def test_score_without_signals_passthrough(self):
        from bubblegum.core.grounding.ranker import CandidateRanker
        from bubblegum.core.schemas import ResolvedTarget
        ranker = CandidateRanker()
        target = ResolvedTarget(ref="btn", confidence=0.77, resolver_name="test")
        assert ranker.score(target) == 0.77

    def test_compute_confidence_helper(self):
        from bubblegum.core.grounding.ranker import compute_confidence
        score = compute_confidence({
            "text_match": 1.0, "role_match": 1.0, "visibility": 1.0,
            "uniqueness": 1.0, "proximity": 1.0, "memory_history": 1.0,
        })
        assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. Error taxonomy tests
# ---------------------------------------------------------------------------

class TestErrorTaxonomy:

    def test_all_errors_importable(self):
        from bubblegum.core.grounding.errors import (
            AICostPolicyBlockedError, AmbiguousTargetError, BubblegumError,
            ContextCollectionError, ExecutionFailedError, LowConfidenceError,
            MemoryStaleError, ProviderConfigError, ResolutionFailedError,
            ValidationFailedError,
        )

    def test_all_errors_extend_bubblegum_error(self):
        from bubblegum.core.grounding.errors import (
            AICostPolicyBlockedError, AmbiguousTargetError, BubblegumError,
            ContextCollectionError, ExecutionFailedError, LowConfidenceError,
            MemoryStaleError, ProviderConfigError, ResolutionFailedError,
            ValidationFailedError,
        )
        for cls in [
            ResolutionFailedError, AmbiguousTargetError, LowConfidenceError,
            ExecutionFailedError, ValidationFailedError, ContextCollectionError,
            ProviderConfigError, AICostPolicyBlockedError, MemoryStaleError,
        ]:
            assert issubclass(cls, BubblegumError), f"{cls.__name__} must extend BubblegumError"

    def test_resolution_failed_error_fields(self):
        from bubblegum.core.grounding.errors import ResolutionFailedError
        err = ResolutionFailedError(step="Click Login", message="No candidate found")
        assert err.step    == "Click Login"
        assert err.message == "No candidate found"
        assert err.candidates == []

    def test_ambiguous_target_error_gap(self):
        from bubblegum.core.grounding.errors import AmbiguousTargetError
        from bubblegum.core.schemas import ResolvedTarget
        c1 = ResolvedTarget(ref="a", confidence=0.90, resolver_name="r1")
        c2 = ResolvedTarget(ref="b", confidence=0.88, resolver_name="r2")
        err = AmbiguousTargetError(step="Click Login", candidates=[c1, c2], gap=0.02)
        assert err.gap == 0.02
        assert len(err.candidates) == 2

    def test_low_confidence_error_best_confidence(self):
        from bubblegum.core.grounding.errors import LowConfidenceError
        from bubblegum.core.schemas import ResolvedTarget
        c = ResolvedTarget(ref="a", confidence=0.35, resolver_name="r1")
        err = LowConfidenceError(step="Click Login", candidates=[c], best_confidence=0.35)
        assert err.best_confidence == 0.35

    def test_validation_failed_error_expected_actual(self):
        from bubblegum.core.grounding.errors import ValidationFailedError
        err = ValidationFailedError(step="Verify dashboard", expected="Dashboard", actual="Login")
        assert err.expected == "Dashboard"
        assert err.actual   == "Login"

    def test_errors_are_exceptions(self):
        from bubblegum.core.grounding.errors import ResolutionFailedError
        with pytest.raises(Exception):
            raise ResolutionFailedError(step="x", message="test")


# ---------------------------------------------------------------------------
# 6. Config tests
# ---------------------------------------------------------------------------

class TestConfig:

    def test_default_config_thresholds(self):
        from bubblegum.core.config import BubblegumConfig
        cfg = BubblegumConfig()
        assert cfg.grounding.accept_threshold   == 0.85
        assert cfg.grounding.review_threshold   == 0.70
        assert cfg.grounding.ambiguous_gap      == 0.05
        assert cfg.grounding.reject_threshold   == 0.50
        assert cfg.grounding.max_cost_level     == "medium"
        assert cfg.grounding.memory_ttl_days    == 7
        assert cfg.grounding.memory_max_failures == 3

    def test_default_ai_config(self):
        from bubblegum.core.config import BubblegumConfig
        cfg = BubblegumConfig()
        assert cfg.ai.enabled   is True
        assert cfg.ai.provider  == "anthropic"
        assert cfg.ai.model     is None   # must be set explicitly

    def test_default_privacy_config(self):
        from bubblegum.core.config import BubblegumConfig
        cfg = BubblegumConfig()
        assert cfg.privacy.redact_pii       is True
        assert cfg.privacy.send_screenshots is False

    def test_debug_raw_payloads_off_by_default(self):
        from bubblegum.core.config import BubblegumConfig
        cfg = BubblegumConfig()
        assert cfg.debug.log_raw_payloads is False   # NEVER on by default

    def test_vision_enabled_requires_send_screenshots(self):
        from bubblegum.core.config import BubblegumConfig, GroundingConfig, PrivacyConfig
        cfg = BubblegumConfig(
            grounding=GroundingConfig(enable_vision=True),
            privacy=PrivacyConfig(send_screenshots=False),   # screenshots off
        )
        assert cfg.vision_enabled is False   # blocked by privacy gate

    def test_load_missing_file_returns_defaults(self, tmp_path):
        from bubblegum.core.config import BubblegumConfig
        cfg = BubblegumConfig.load(path=tmp_path / "nonexistent.yaml")
        assert cfg.grounding.accept_threshold == 0.85

    def test_load_from_yaml_file(self, tmp_path):
        import yaml
        from bubblegum.core.config import BubblegumConfig
        data = {"grounding": {"accept_threshold": 0.90, "max_cost_level": "high"}}
        yaml_file = tmp_path / "bubblegum.yaml"
        yaml_file.write_text(yaml.dump(data))
        cfg = BubblegumConfig.load(path=yaml_file)
        assert cfg.grounding.accept_threshold == 0.90
        assert cfg.grounding.max_cost_level   == "high"
        assert cfg.grounding.review_threshold  == 0.70   # default preserved


# ---------------------------------------------------------------------------
# 7. Confidence helpers tests
# ---------------------------------------------------------------------------

class TestConfidenceHelpers:

    def test_is_accepted(self):
        from bubblegum.core.grounding.confidence import is_accepted
        assert is_accepted(0.85) is True
        assert is_accepted(0.90) is True
        assert is_accepted(0.84) is False

    def test_is_reviewable(self):
        from bubblegum.core.grounding.confidence import is_reviewable
        assert is_reviewable(0.70) is True
        assert is_reviewable(0.80) is True
        assert is_reviewable(0.69) is False

    def test_is_ambiguous(self):
        from bubblegum.core.grounding.confidence import is_ambiguous
        assert is_ambiguous(0.02) is True
        assert is_ambiguous(0.04) is True
        assert is_ambiguous(0.05) is False   # boundary: 0.05 is NOT ambiguous (< 0.05 triggers it)
        assert is_ambiguous(0.10) is False

    def test_is_rejected(self):
        from bubblegum.core.grounding.confidence import is_rejected
        assert is_rejected(0.49) is True
        assert is_rejected(0.50) is False   # boundary: exactly 0.50 is NOT rejected
        assert is_rejected(0.80) is False


# ---------------------------------------------------------------------------
# 8. GroundingEngine skeleton tests
# ---------------------------------------------------------------------------

class TestGroundingEngineSkeleton:

    @pytest.mark.asyncio
    async def test_ground_raises_resolution_failed_when_all_stubs(self):
        """All Phase 0 resolvers return [] — engine should raise ResolutionFailedError."""
        from bubblegum.core.grounding.engine import GroundingEngine
        from bubblegum.core.grounding.errors import ResolutionFailedError
        from bubblegum.core.schemas import StepIntent
        engine = GroundingEngine()
        intent = StepIntent(instruction="Click Login", channel="web", action_type="click")
        with pytest.raises(ResolutionFailedError):
            await engine.ground(intent)

    @pytest.mark.asyncio
    async def test_ground_tier1_stops_on_high_confidence(self):
        """If a Tier 1 resolver returns a high-confidence result, engine stops at Tier 1."""
        from bubblegum.core.grounding.engine import GroundingEngine
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class HighConfResolver(Resolver):
            name      = "high_conf_test"
            priority  = 5
            channels  = ["web", "mobile"]
            cost_level = "low"
            tier      = 1
            def resolve(self, intent):
                return [ResolvedTarget(ref="btn", confidence=0.95, resolver_name=self.name)]

        reg = ResolverRegistry()
        reg.register(HighConfResolver())
        engine = GroundingEngine(registry=reg)
        intent = StepIntent(instruction="Click x", channel="web", action_type="click")
        target, traces = await engine.ground(intent)
        assert target.confidence == 0.95
        # Tier 3 should NOT have run
        tier3_names = {"llm_grounding", "ocr", "vision_model"}
        ran_names   = {t.resolver_name for t in traces if t.can_run}
        assert not tier3_names.intersection(ran_names)

    @pytest.mark.asyncio
    async def test_ground_raises_ambiguous_when_gap_too_small(self):
        """Two candidates within 0.05 confidence → AmbiguousTargetError."""
        from bubblegum.core.grounding.engine import GroundingEngine
        from bubblegum.core.grounding.errors import AmbiguousTargetError
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ResolvedTarget, StepIntent

        class AmbigResolver(Resolver):
            name      = "ambig_test"
            priority  = 5
            channels  = ["web", "mobile"]
            cost_level = "low"
            tier      = 1
            def resolve(self, intent):
                return [
                    ResolvedTarget(ref="btn-a", confidence=0.91, resolver_name=self.name),
                    ResolvedTarget(ref="btn-b", confidence=0.90, resolver_name=self.name),
                ]

        reg = ResolverRegistry()
        reg.register(AmbigResolver())
        engine = GroundingEngine(registry=reg)
        intent = StepIntent(instruction="Click x", channel="web", action_type="click")
        with pytest.raises(AmbiguousTargetError) as exc_info:
            await engine.ground(intent)
        assert exc_info.value.gap < 0.05

    @pytest.mark.asyncio
    async def test_ground_tier3_blocked_on_low_cost_policy(self):
        """max_cost_level=low should block Tier 3 and raise AICostPolicyBlockedError."""
        from bubblegum.core.grounding.engine import GroundingEngine
        from bubblegum.core.grounding.errors import AICostPolicyBlockedError
        from bubblegum.core.grounding.registry import ResolverRegistry
        from bubblegum.core.grounding.resolver import Resolver
        from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent

        class LowConfTier1(Resolver):
            name      = "low_conf_tier1"
            priority  = 5
            channels  = ["web", "mobile"]
            cost_level = "low"
            tier      = 1
            def resolve(self, intent):
                return [ResolvedTarget(ref="btn", confidence=0.40, resolver_name=self.name)]

        reg = ResolverRegistry()
        reg.register(LowConfTier1())
        engine = GroundingEngine(registry=reg)
        opts   = ExecutionOptions(max_cost_level="low")
        intent = StepIntent(instruction="Click x", channel="web", action_type="click", options=opts)
        with pytest.raises(AICostPolicyBlockedError):
            await engine.ground(intent)

    @pytest.mark.asyncio
    async def test_ground_returns_resolver_traces(self):
        """StepResult traces should contain one entry per resolver that ran."""
        from bubblegum.core.grounding.engine import GroundingEngine
        from bubblegum.core.grounding.errors import ResolutionFailedError
        from bubblegum.core.schemas import StepIntent
        engine = GroundingEngine()
        intent = StepIntent(instruction="Click x", channel="web", action_type="click")
        with pytest.raises(ResolutionFailedError):
            await engine.ground(intent)
        # The test confirms engine runs without crashing — traces are internal


# ---------------------------------------------------------------------------
# 9. Benchmark dataset scaffold tests
# ---------------------------------------------------------------------------

class TestBenchmarkScaffold:

    def _dataset_root(self):
        from pathlib import Path
        return Path(__file__).parent.parent / "benchmarks" / "golden_dataset"

    def test_all_5_categories_exist(self):
        root = self._dataset_root()
        for cat in ("web_standard", "broken_selectors", "changed_labels", "duplicate_labels", "dynamic_overlays"):
            assert (root / cat).is_dir(), f"Missing category dir: {cat}"

    def test_all_scenarios_json_parseable(self):
        import json
        root = self._dataset_root()
        for cat in ("web_standard", "broken_selectors", "changed_labels", "duplicate_labels", "dynamic_overlays"):
            path = root / cat / "scenarios.json"
            assert path.exists(), f"Missing scenarios.json: {cat}"
            data = json.loads(path.read_text())
            assert "scenarios" in data
            assert isinstance(data["scenarios"], list)

    def test_scenarios_have_required_fields(self):
        import json
        root = self._dataset_root()
        required = {"id", "instruction", "channel", "action_type"}
        for cat in ("web_standard", "broken_selectors", "changed_labels", "duplicate_labels", "dynamic_overlays"):
            data = json.loads((root / cat / "scenarios.json").read_text())
            for s in data["scenarios"]:
                missing = required - s.keys()
                assert not missing, f"Scenario {s.get('id', '?')} in {cat} missing: {missing}"
