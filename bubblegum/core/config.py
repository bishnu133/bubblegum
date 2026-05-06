"""
bubblegum/core/config.py
=========================
BubblegumConfig — typed config loader for bubblegum.yaml.

Reads the YAML file from the project root (or a path passed explicitly).
All sections map to nested Pydantic models so the rest of the codebase
can access config values with full type safety and IDE auto-complete.

Phase 0 — schema + loader. No runtime wiring to engine/adapters yet.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("bubblegum.yaml")


# ---------------------------------------------------------------------------
# Config section models
# ---------------------------------------------------------------------------

class GroundingConfig(BaseModel):
    accept_threshold:   float = 0.85
    review_threshold:   float = 0.70
    ambiguous_gap:      float = 0.05
    reject_threshold:   float = 0.50
    max_cost_level:     str   = "medium"   # "low" | "medium" | "high"
    enable_vision:      bool  = False
    enable_ocr:         bool  = True
    memory_ttl_days:    int   = 7
    memory_max_failures: int  = 3


class AIConfig(BaseModel):
    enabled:  bool        = True
    provider: str         = "anthropic"    # anthropic | openai | gemini | local
    model:    str | None  = None           # must be set explicitly; no surprise API costs


class PrivacyConfig(BaseModel):
    redact_pii:         bool = True
    send_screenshots:   bool = False       # must be True to enable VisionModelResolver
    log_provider_calls: bool = True
    process_screenshots_for_ocr: bool = False  # explicit opt-in for screenshot OCR pipeline


class DebugConfig(BaseModel):
    log_raw_payloads:   bool = False       # NEVER enable in CI or production
    log_resolver_traces: bool = True       # safe — logs resolver names + confidence only


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

class BubblegumConfig(BaseModel):
    """
    Typed representation of bubblegum.yaml.

    Usage:
        config = BubblegumConfig.load()                     # reads ./bubblegum.yaml
        config = BubblegumConfig.load("path/to/other.yaml") # explicit path
        config = BubblegumConfig()                          # all defaults (testing)
    """

    grounding: GroundingConfig = Field(default_factory=GroundingConfig)
    ai:        AIConfig        = Field(default_factory=AIConfig)
    privacy:   PrivacyConfig   = Field(default_factory=PrivacyConfig)
    debug:     DebugConfig     = Field(default_factory=DebugConfig)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BubblegumConfig":
        """
        Load config from a YAML file.

        Search order:
          1. Explicit path argument (if provided)
          2. BUBBLEGUM_CONFIG env var (if set)
          3. ./bubblegum.yaml (project root)

        If no file is found, returns a BubblegumConfig with all defaults.
        This allows Bubblegum to run in zero-config mode for quick trials.
        """
        import os

        resolved_path: Path | None = None

        if path is not None:
            resolved_path = Path(path)
        elif env_path := os.environ.get("BUBBLEGUM_CONFIG"):
            resolved_path = Path(env_path)
        elif _DEFAULT_CONFIG_PATH.exists():
            resolved_path = _DEFAULT_CONFIG_PATH

        if resolved_path is None:
            logger.info("No bubblegum.yaml found — using all defaults.")
            return cls()

        if not resolved_path.exists():
            logger.warning("Config file not found at %s — using all defaults.", resolved_path)
            return cls()

        raw = _load_yaml(resolved_path)
        config = cls.model_validate(raw)
        logger.info("Loaded config from %s", resolved_path)
        return config

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def ai_enabled(self) -> bool:
        return self.ai.enabled

    @property
    def vision_enabled(self) -> bool:
        return self.grounding.enable_vision and self.privacy.send_screenshots

    @property
    def ocr_enabled(self) -> bool:
        return self.grounding.enable_ocr

    @property
    def debug_mode(self) -> bool:
        return self.debug.log_raw_payloads


# ---------------------------------------------------------------------------
# YAML loader (stdlib only — no extra dependency)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """
    Load a YAML file using PyYAML if available, otherwise raise a clear error.
    PyYAML is listed as a dependency in pyproject.toml — this error should not
    occur in practice, but gives a helpful message if the env is broken.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load bubblegum.yaml. "
            "Install it with: pip install pyyaml"
        ) from exc

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    return data or {}


# ---------------------------------------------------------------------------
# Example bubblegum.yaml — written out for reference / project scaffold
# ---------------------------------------------------------------------------

EXAMPLE_YAML = """\
# bubblegum.yaml — Bubblegum configuration
# Place this file in your project root.

grounding:
  accept_threshold: 0.85
  review_threshold: 0.70
  ambiguous_gap: 0.05
  reject_threshold: 0.50
  max_cost_level: medium   # low | medium | high
  enable_vision: false
  enable_ocr: true
  memory_ttl_days: 7
  memory_max_failures: 3

ai:
  enabled: true
  provider: anthropic          # anthropic | openai | gemini | local
  model: <your-model-name>     # e.g. claude-sonnet-latest — must be set explicitly

privacy:
  redact_pii: true
  send_screenshots: false      # set to true only to enable VisionModelResolver
  log_provider_calls: true
  process_screenshots_for_ocr: false  # explicit opt-in for screenshot OCR pipeline

debug:
  log_raw_payloads: false      # NEVER enable in CI or production
  log_resolver_traces: true    # safe — logs resolver names + confidence only
"""
