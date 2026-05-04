from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bubblegum.core.config import BubblegumConfig


def test_load_explicit_path_overrides_env_and_default(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text(
        yaml.dump({"grounding": {"accept_threshold": 0.91}, "ai": {"enabled": False}}),
        encoding="utf-8",
    )

    env_cfg = tmp_path / "env.yaml"
    env_cfg.write_text(yaml.dump({"grounding": {"accept_threshold": 0.77}}), encoding="utf-8")

    monkeypatch.setenv("BUBBLEGUM_CONFIG", str(env_cfg))

    # Also create a cwd default file to ensure explicit wins over default too
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bubblegum.yaml").write_text(
        yaml.dump({"grounding": {"accept_threshold": 0.66}}),
        encoding="utf-8",
    )

    cfg = BubblegumConfig.load(path=explicit)
    assert cfg.grounding.accept_threshold == 0.91
    assert cfg.ai.enabled is False


def test_load_uses_env_path_when_explicit_not_supplied(tmp_path, monkeypatch):
    env_cfg = tmp_path / "from-env.yaml"
    env_cfg.write_text(
        yaml.dump({"grounding": {"memory_ttl_days": 13}, "ai": {"enabled": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLEGUM_CONFIG", str(env_cfg))

    cfg = BubblegumConfig.load()
    assert cfg.grounding.memory_ttl_days == 13
    assert cfg.ai.enabled is False


def test_load_missing_explicit_file_returns_defaults(tmp_path):
    missing = tmp_path / "does-not-exist.yaml"
    cfg = BubblegumConfig.load(path=missing)

    # Current implementation warns and falls back to defaults.
    assert cfg.grounding.accept_threshold == 0.85
    assert cfg.grounding.memory_ttl_days == 7
    assert cfg.grounding.memory_max_failures == 3


def test_load_malformed_yaml_raises(tmp_path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("grounding: [unclosed", encoding="utf-8")

    with pytest.raises(Exception):
        BubblegumConfig.load(path=broken)


def test_convenience_properties_defaults_and_toggles():
    cfg = BubblegumConfig()
    assert cfg.ai_enabled is True
    assert cfg.vision_enabled is False  # send_screenshots defaults false
    assert cfg.ocr_enabled is True
    assert cfg.debug_mode is False

    cfg.grounding.enable_vision = True
    cfg.privacy.send_screenshots = True
    cfg.ai.enabled = False
    cfg.grounding.enable_ocr = False
    cfg.debug.log_raw_payloads = True

    assert cfg.vision_enabled is True
    assert cfg.ai_enabled is False
    assert cfg.ocr_enabled is False
    assert cfg.debug_mode is True
