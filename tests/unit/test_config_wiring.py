import pytest

from bubblegum.core.config import BubblegumConfig, GroundingConfig
from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent, UIContext
from bubblegum.core.sdk import _build_options, _merge_context, configure_runtime


def test_configure_runtime_wires_grounding_thresholds():
    cfg = BubblegumConfig(
        grounding=GroundingConfig(
            accept_threshold=0.91,
            review_threshold=0.74,
            ambiguous_gap=0.03,
            reject_threshold=0.55,
            max_cost_level="low",
        )
    )

    configure_runtime(config=cfg)

    from bubblegum.core import sdk

    assert sdk._engine.accept_threshold == 0.91
    assert sdk._engine.review_threshold == 0.74
    assert sdk._engine.ambiguous_gap == 0.03
    assert sdk._engine.reject_threshold == 0.55


def test_build_options_defaults_from_runtime_config():
    cfg = BubblegumConfig()
    cfg.ai.enabled = False
    cfg.grounding.max_cost_level = "low"
    cfg.grounding.memory_ttl_days = 11
    cfg.grounding.memory_max_failures = 5

    configure_runtime(config=cfg)
    opts = _build_options({})

    assert opts.use_ai is False
    assert opts.max_cost_level == "low"
    assert opts.memory_ttl_days == 11
    assert opts.memory_max_failures == 5


def test_build_options_explicit_kwargs_override_runtime_config():
    cfg = BubblegumConfig()
    cfg.ai.enabled = False
    cfg.grounding.max_cost_level = "low"
    cfg.grounding.memory_ttl_days = 7
    cfg.grounding.memory_max_failures = 3

    configure_runtime(config=cfg)
    opts = _build_options({
        "use_ai": True,
        "max_cost_level": "high",
        "memory_ttl_days": 14,
        "memory_max_failures": 8,
    })

    assert opts.use_ai is True
    assert opts.max_cost_level == "high"
    assert opts.memory_ttl_days == 14
    assert opts.memory_max_failures == 8


def test_safe_default_config_loading_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BUBBLEGUM_CONFIG", raising=False)

    cfg = BubblegumConfig.load()

    assert cfg.grounding.accept_threshold == 0.85
    assert cfg.grounding.memory_ttl_days == 7
    assert cfg.grounding.memory_max_failures == 3
    assert cfg.privacy.process_screenshots_for_vision is False


def test_yaml_override_via_temp_config_file(tmp_path):
    import yaml

    cfg_file = tmp_path / "custom-bubblegum.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "grounding": {
                    "accept_threshold": 0.93,
                    "memory_ttl_days": 21,
                    "memory_max_failures": 9,
                },
                "ai": {"enabled": False},
                "privacy": {"process_screenshots_for_vision": True},
            }
        ),
        encoding="utf-8",
    )

    cfg = BubblegumConfig.load(path=cfg_file)

    assert cfg.grounding.accept_threshold == 0.93
    assert cfg.grounding.memory_ttl_days == 21
    assert cfg.grounding.memory_max_failures == 9
    assert cfg.ai.enabled is False
    assert cfg.privacy.process_screenshots_for_vision is True


def test_ocr_vision_flags_respected_via_resolver_eligibility():
    cfg = BubblegumConfig()
    cfg.grounding.enable_ocr = False
    cfg.grounding.enable_vision = True
    cfg.privacy.send_screenshots = False
    configure_runtime(config=cfg)

    intent = StepIntent(instruction="Click login", channel="web", action_type="click")
    _merge_context(intent, UIContext())

    registry = ResolverRegistry()
    ocr = registry.get("ocr")
    vision = registry.get("vision_model")

    assert ocr is not None
    assert vision is not None
    assert ocr.can_run(intent) is False
    assert vision.can_run(intent) is False


def test_webview_switching_config_defaults_in_runtime():
    cfg = BubblegumConfig()
    configure_runtime(config=cfg)
    from bubblegum.core import sdk

    assert sdk._config.webview_switching.webview_switching_mode == "off"
    assert sdk._config.webview_switching.enable_webview_switching is False


# ---------------------------------------------------------------------------
# C0 — config thresholds provably change resolver/tier BEHAVIOR (not just the
# stored attribute). The other tests above assert the value is wired onto the
# engine; this one proves the engine actually *reads* accept_threshold at a
# decision point, by showing an extreme value reroutes resolution to a later
# tier. Acceptance criterion: "Changing any threshold in bubblegum.yaml
# provably changes resolver/tier behavior, covered by a test."
# ---------------------------------------------------------------------------


class _Tier1Resolver(Resolver):
    """Deterministic Tier-1 match just above the default accept_threshold."""

    name = "c0_tier1_test"
    priority = 5
    channels = ["web", "mobile"]
    cost_level = "low"
    tier = 1

    def resolve(self, intent):
        return [ResolvedTarget(ref="tier1-btn", confidence=0.86, resolver_name=self.name)]


class _Tier2Resolver(Resolver):
    """A different element resolved in Tier 2, inside the review band."""

    name = "c0_tier2_test"
    priority = 45
    channels = ["web", "mobile"]
    cost_level = "low"
    tier = 2

    def resolve(self, intent):
        return [ResolvedTarget(ref="tier2-btn", confidence=0.80, resolver_name=self.name)]


def _registry_with_c0_resolvers() -> ResolverRegistry:
    reg = ResolverRegistry()
    reg.register(_Tier1Resolver())
    reg.register(_Tier2Resolver())
    return reg


@pytest.mark.asyncio
async def test_accept_threshold_change_reroutes_tier_resolution():
    """
    With the default accept_threshold (0.85) the Tier-1 0.86 candidate is
    accepted and returned at Tier 1. Raising accept_threshold to an extreme
    0.999 must make that same match fall through to Tier 2 — proving the
    threshold is honored at the decision point rather than hardcoded.
    """
    intent = StepIntent(
        instruction="Click x",
        channel="web",
        action_type="click",
        options=ExecutionOptions(max_cost_level="high"),
    )

    # Default accept_threshold: Tier 1 wins.
    default_engine = GroundingEngine(registry=_registry_with_c0_resolvers())
    target, _ = await default_engine.ground(intent)
    assert target.ref == "tier1-btn"
    assert target.resolver_name == "c0_tier1_test"

    # Extreme accept_threshold: the identical Tier-1 match no longer accepts,
    # so resolution falls through to the Tier-2 resolver.
    strict_engine = GroundingEngine(
        registry=_registry_with_c0_resolvers(),
        accept_threshold=0.999,
    )
    target, _ = await strict_engine.ground(intent)
    assert target.ref == "tier2-btn"
    assert target.resolver_name == "c0_tier2_test"


@pytest.mark.asyncio
async def test_accept_threshold_from_config_changes_behavior_end_to_end():
    """
    Same proof, but driving the threshold through BubblegumConfig /
    configure_runtime exactly as a bubblegum.yaml value would — closing the
    loop from YAML config to live tier behavior.
    """
    intent = StepIntent(
        instruction="Click x",
        channel="web",
        action_type="click",
        options=ExecutionOptions(max_cost_level="high"),
    )

    configure_runtime(
        config=BubblegumConfig(grounding=GroundingConfig(accept_threshold=0.999))
    )
    from bubblegum.core import sdk

    strict_engine = GroundingEngine(
        registry=_registry_with_c0_resolvers(),
        accept_threshold=sdk._engine.accept_threshold,
    )
    target, _ = await strict_engine.ground(intent)
    assert target.ref == "tier2-btn"

    # Restore default runtime config so global engine state does not leak into
    # other tests that rely on the 0.85 default.
    configure_runtime(config=BubblegumConfig())
