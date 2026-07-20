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
    # X2: per-run hard cost ceiling (USD) for Tier-3 AI calls. 0 == disabled.
    # Once the run's estimated LLM spend reaches this, Tier 3 is hard-stopped.
    max_run_cost_usd:   float = 0.0
    enable_vision:      bool  = False
    enable_ocr:         bool  = True
    # Semantic (embedding) Tier-2 matching (Task #4). Catches meaning-level label
    # drift ("Submit"->"Continue") that edit-distance fuzzy matching misses,
    # before falling to the costlier LLM tier. Gated here AND by an embedding
    # provider being configured (ai.embedding_model) or injected — so it stays
    # dormant (zero network/cost) until a team opts in.
    enable_semantic:    bool  = True
    # Minimum cosine similarity for a semantic candidate to be emitted. Higher =
    # stricter (fewer false positives); lower = more recall.
    semantic_min_similarity: float = 0.72
    # X3: when a vision/OCR target cannot be deterministically hydrated to a
    # DOM/hierarchy element (canvas, image-only, custom-drawn UI), fall back to
    # clicking the bounding-box center coordinate. Opt-in — a blind coordinate
    # click is riskier than an element click, so it is OFF by default.
    coordinate_click_fallback: bool = False
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


class VisualConfig(BaseModel):
    """Visual-regression settings (verify(..., assertion_type='visual'))."""

    # Where baseline images (and diff/actual artifacts) live.
    baseline_dir: str = ".bubblegum/baselines"
    # Fraction of pixels (0.0–1.0) allowed to differ before the check fails.
    tolerance: float = 0.001
    # Per-channel 0–255 delta below which a pixel counts as unchanged — absorbs
    # anti-aliasing / sub-pixel noise. 0 means any difference counts.
    channel_threshold: int = 0
    # Capture the full scrollable page instead of just the viewport.
    full_page: bool = False
    # When True, (re)write baselines instead of comparing — first-run capture or
    # an intentional UI change. Usually toggled via --bubblegum-update-baselines.
    update_baselines: bool = False

    @field_validator("tolerance")
    @classmethod
    def _validate_tolerance(cls, value: float) -> float:
        f = float(value)
        if not (0.0 <= f <= 1.0):
            raise ValueError("tolerance must be between 0.0 and 1.0")
        return f

    @field_validator("channel_threshold")
    @classmethod
    def _validate_channel_threshold(cls, value: int) -> int:
        i = int(value)
        if not (0 <= i <= 255):
            raise ValueError("channel_threshold must be between 0 and 255")
        return i


class MobileConfig(BaseModel):
    """Mobile channel behavior (M2)."""

    # Best-effort: hide the soft keyboard before a tap/click. Off by default;
    # enable when keyboard occlusion makes taps below the keyboard flaky. The
    # soft keyboard is a top Appium flakiness source (IME state).
    auto_hide_keyboard: bool = False
    # Default seconds to keep the app backgrounded for "background app" before
    # it auto-foregrounds.
    background_app_seconds: int = 3


class FlakyConfig(BaseModel):
    """Flaky-test detection / quarantine settings (X1)."""

    enabled: bool = True
    # A step is flagged flaky when its historical pass-rate is below this AND it
    # has both passed and failed at least once (intermittent, not just broken).
    stability_threshold: float = 0.90
    # Minimum observed runs before a step can be judged flaky (avoids noise).
    min_runs: int = 3
    # When True, a flaky step's failure is reported but does not fail the build
    # (mark-but-not-fail). Usually toggled via --bubblegum-quarantine.
    quarantine: bool = False

    @field_validator("stability_threshold")
    @classmethod
    def _validate_stability(cls, value: float) -> float:
        f = float(value)
        if not (0.0 <= f <= 1.0):
            raise ValueError("stability_threshold must be between 0.0 and 1.0")
        return f

    @field_validator("min_runs")
    @classmethod
    def _validate_min_runs(cls, value: int) -> int:
        i = int(value)
        if i < 1:
            raise ValueError("min_runs must be >= 1")
        return i


class AIConfig(BaseModel):
    enabled:  bool        = True
    provider: str         = "anthropic"    # anthropic | openai | gemini | local
    model:    str | None  = None           # must be set explicitly; no surprise API costs

    # --- Tiered model routing (Task #2) --------------------------------------
    # fast_model handles the high-volume, latency-sensitive work (grounding,
    # instruction decomposition); strong_model is an optional escalation target
    # used only when the fast model resolves below the review threshold AND
    # escalate_on_low_confidence is true. Both default to `model` when unset, so
    # existing single-model configs behave exactly as before.
    fast_model:   str | None = None        # e.g. claude-haiku-4-5 / gpt-4o-mini
    strong_model: str | None = None        # e.g. claude-sonnet-4-6 / gpt-4o
    escalate_on_low_confidence: bool = False

    # --- Embeddings (Task #4 semantic Tier-2) --------------------------------
    # embedding_model activates the semantic resolver. embedding_provider
    # defaults to `provider` when unset. Only "openai" has a built-in embeddings
    # backend; other providers require an injected provider via
    # configure_embedding_provider() (e.g. offline sentence-transformers).
    embedding_provider: str | None = None
    embedding_model:    str | None = None   # e.g. text-embedding-3-small

    # --- Call tuning ----------------------------------------------------------
    max_tokens:     int  = 1024            # max completion tokens per grounding call
    prompt_caching: bool = True            # apply provider-native prompt caching where supported

    def resolved_fast_model(self) -> str | None:
        """Model used for grounding/decompose — fast_model, else the base model."""
        return self.fast_model or self.model

    def resolved_strong_model(self) -> str | None:
        """Escalation model — strong_model, else the base model."""
        return self.strong_model or self.model


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
    visual:    VisualConfig     = Field(default_factory=VisualConfig)
    mobile:    MobileConfig      = Field(default_factory=MobileConfig)
    flaky:     FlakyConfig       = Field(default_factory=FlakyConfig)
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
  max_run_cost_usd: 0.0    # per-run Tier-3 cost ceiling in USD (0 = disabled)
  enable_vision: false
  enable_ocr: true
  enable_semantic: true    # embedding-based Tier-2 match (needs ai.embedding_model to activate)
  semantic_min_similarity: 0.72  # min cosine similarity to emit a semantic candidate
  coordinate_click_fallback: false  # click bbox-center when a vision/OCR target can't map to an element (X3)
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

visual:
  baseline_dir: .bubblegum/baselines
  tolerance: 0.001                 # fraction of pixels (0.0–1.0) allowed to differ
  channel_threshold: 0             # per-channel 0–255 delta ignored (anti-aliasing noise)
  full_page: false                 # capture full scrollable page vs viewport
  update_baselines: false          # or pass --bubblegum-update-baselines

mobile:
  auto_hide_keyboard: false        # hide the soft keyboard before a tap/click
  background_app_seconds: 3        # default duration for "background app"

flaky:
  enabled: true
  stability_threshold: 0.90        # pass-rate below this (with ≥1 pass and ≥1 fail) → flaky
  min_runs: 3                      # minimum runs before judging flakiness
  quarantine: false                # or pass --bubblegum-quarantine (mark-but-not-fail)

ai:
  enabled: true
  provider: anthropic          # anthropic | openai | gemini | local
  model: <your-model-name>     # e.g. claude-sonnet-latest — must be set explicitly
  # Tiered routing (optional). Both default to `model` when unset.
  # fast_model: claude-haiku-4-5      # cheap/fast model for grounding + decompose
  # strong_model: claude-sonnet-4-6   # escalation model for hard cases
  # escalate_on_low_confidence: false # retry with strong_model when fast is unsure
  max_tokens: 1024             # max completion tokens per grounding call
  prompt_caching: true         # use provider-native prompt caching where supported
  # Semantic Tier-2 embeddings (optional). Set embedding_model to activate.
  # embedding_provider: openai            # defaults to `provider` when unset
  # embedding_model: text-embedding-3-small

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
