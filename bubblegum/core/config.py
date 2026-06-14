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

from pydantic import BaseModel, Field, field_validator

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
    ai_first:           bool  = False      # try AI (vision/LLM) tier before deterministic tiers
    memory_ttl_days:    int   = 7
    memory_max_failures: int  = 3
    # Re-ground retries for late-rendered (SPA) elements — see ExecutionOptions.
    resolve_retries:    int   = 2
    resolve_retry_interval_ms: int = 300
    # Stability / quiescence wait (W2): before resolving, wait until the page
    # settles — no DOM mutations for stability_quiet_ms, no in-flight network,
    # and no visible loading indicator — bounded by stability_timeout_ms.
    stability_wait_enabled: bool = True
    stability_quiet_ms:     int  = 400
    stability_timeout_ms:   int  = 5_000
    stability_spinner_selectors: list[str] = Field(
        default_factory=lambda: [
            "[aria-busy='true']",
            "[role='progressbar']",
            ".spinner",
            ".loading",
            ".loader",
            "[class*='spinner']",
            "[class*='loading']",
        ]
    )


class A11yConfig(BaseModel):
    """Accessibility-assertion settings (verify(..., assertion_type='a11y'))."""

    # Path to an axe-core build to inject. Defaults to the vendored copy
    # shipped with Bubblegum (offline, zero-config). Override to pin your own.
    axe_script_path: str | None = None
    # Optional remote/CDN URL to load axe-core from instead of the local file.
    # When set, takes precedence over axe_script_path. Requires network access.
    axe_url: str | None = None
    # Minimum violation impact that fails the assertion: any violation at or
    # above this level fails. One of: minor | moderate | serious | critical.
    impact_threshold: str = "critical"

    @field_validator("impact_threshold")
    @classmethod
    def _validate_impact(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        allowed = {"minor", "moderate", "serious", "critical"}
        if normalized not in allowed:
            raise ValueError(f"impact_threshold must be one of {sorted(allowed)}")
        return normalized


class AIConfig(BaseModel):
    enabled:  bool        = True
    provider: str         = "anthropic"    # anthropic | openai | gemini | local
    model:    str | None  = None           # must be set explicitly; no surprise API costs


class PrivacyConfig(BaseModel):
    redact_pii:         bool = True
    send_screenshots:   bool = False       # must be True to enable VisionModelResolver
    log_provider_calls: bool = True
    process_screenshots_for_vision: bool = False  # explicit opt-in for screenshot vision pipeline
    process_screenshots_for_ocr: bool = False  # explicit opt-in for screenshot OCR pipeline


class DebugConfig(BaseModel):
    log_raw_payloads:   bool = False       # NEVER enable in CI or production
    log_resolver_traces: bool = True       # safe — logs resolver names + confidence only


class WebviewSwitchingConfig(BaseModel):
    enable_webview_switching: bool = False
    webview_switching_mode: str = "off"  # off | dry_run | opt_in
    webview_switch_allowed_operations: list[str] = Field(default_factory=list)
    require_restore_context: bool = True
    fail_closed_on_restore_failure: bool = True
    webview_context_selection_policy: str = "single_webview_only"  # single_webview_only | first_available | hint_match
    max_webview_switch_attempts: int = 1
    webview_readiness_wait_enabled: bool = False
    webview_context_wait_timeout_ms: int = 0
    webview_context_poll_interval_ms: int = 250
    webview_target_wait_timeout_ms: int = 0
    max_context_refresh_attempts: int = 1
    fail_closed_on_readiness_timeout: bool = True

    @field_validator("webview_switching_mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        allowed = {"off", "dry_run", "opt_in"}
        if normalized not in allowed:
            raise ValueError(f"webview_switching_mode must be one of {sorted(allowed)}")
        return normalized

    @field_validator("webview_context_selection_policy")
    @classmethod
    def _validate_selection_policy(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        allowed = {"single_webview_only", "first_available", "hint_match"}
        if normalized not in allowed:
            raise ValueError(f"webview_context_selection_policy must be one of {sorted(allowed)}")
        return normalized

    @field_validator("max_webview_switch_attempts")
    @classmethod
    def _validate_max_attempts(cls, value: int) -> int:
        if int(value) < 1:
            raise ValueError("max_webview_switch_attempts must be >= 1")
        return int(value)


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
    a11y:      A11yConfig       = Field(default_factory=A11yConfig)
    ai:        AIConfig        = Field(default_factory=AIConfig)
    privacy:   PrivacyConfig   = Field(default_factory=PrivacyConfig)
    debug:     DebugConfig     = Field(default_factory=DebugConfig)
    webview_switching: WebviewSwitchingConfig = Field(default_factory=WebviewSwitchingConfig)

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
  ai_first: false          # true = try AI (vision/LLM) before deterministic resolvers
  memory_ttl_days: 7
  memory_max_failures: 3
  resolve_retries: 2               # re-ground attempts for late-rendered SPA elements
  resolve_retry_interval_ms: 300   # delay between re-ground attempts
  stability_wait_enabled: true     # wait for the page to settle before resolving
  stability_quiet_ms: 400          # require this much DOM/network/spinner quiet
  stability_timeout_ms: 5000       # give up settling after this long (then proceed)
  # stability_spinner_selectors: ["[role='progressbar']", ".spinner"]  # override defaults

a11y:
  # axe_script_path: path/to/axe.min.js   # defaults to the vendored axe-core build
  # axe_url: https://cdn.example.com/axe.min.js  # optional remote override
  impact_threshold: critical       # minor | moderate | serious | critical

ai:
  enabled: true
  provider: anthropic          # anthropic | openai | gemini | local
  model: <your-model-name>     # e.g. claude-sonnet-latest — must be set explicitly

privacy:
  redact_pii: true
  send_screenshots: false      # set to true only to enable VisionModelResolver
  log_provider_calls: true
  process_screenshots_for_vision: false  # explicit opt-in for screenshot vision pipeline
  process_screenshots_for_ocr: false  # explicit opt-in for screenshot OCR pipeline

debug:
  log_raw_payloads: false      # NEVER enable in CI or production
  log_resolver_traces: true    # safe — logs resolver names + confidence only
"""
