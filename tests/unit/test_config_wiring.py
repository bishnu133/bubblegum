from bubblegum.core.config import BubblegumConfig, GroundingConfig
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import StepIntent, UIContext
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
            }
        ),
        encoding="utf-8",
    )

    cfg = BubblegumConfig.load(path=cfg_file)

    assert cfg.grounding.accept_threshold == 0.93
    assert cfg.grounding.memory_ttl_days == 21
    assert cfg.grounding.memory_max_failures == 9
    assert cfg.ai.enabled is False


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
