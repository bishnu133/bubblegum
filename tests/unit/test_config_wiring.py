from bubblegum.core.config import BubblegumConfig, GroundingConfig
from bubblegum.core.sdk import _build_options, configure_runtime


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

    configure_runtime(config=cfg)
    opts = _build_options({})

    assert opts.use_ai is False
    assert opts.max_cost_level == "low"


def test_build_options_explicit_kwargs_override_runtime_config():
    cfg = BubblegumConfig()
    cfg.ai.enabled = False
    cfg.grounding.max_cost_level = "low"

    configure_runtime(config=cfg)
    opts = _build_options({"use_ai": True, "max_cost_level": "high"})

    assert opts.use_ai is True
    assert opts.max_cost_level == "high"
