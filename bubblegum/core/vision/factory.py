"""
bubblegum/core/vision/factory.py
================================
get_vision_provider() — build the configured screenshot-grounding backend (Task #6).

Selects a VisionProvider from grounding.vision_backend so screenshot grounding
is reachable from config (like the LLM and embedding tiers) instead of requiring
a manual configure_vision_provider() call. Returns None (dormant) when the
backend is "none"/"callable" or cannot be built — never raises, so a
misconfigured backend degrades to the deterministic + text-LLM tiers.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_vision_provider(config):
    """Return a VisionProvider for the configured backend, or None.

    backends:
      none      -> None (dormant)
      anthropic -> Claude vision   (needs ai.vision_model, hosted)
      openai    -> GPT vision      (needs ai.vision_model, hosted)
      http      -> self-hosted grounder at grounding.vision_endpoint
      callable  -> None (inject via configure_vision_provider())
    """
    backend = (getattr(config.grounding, "vision_backend", "none") or "none").lower().strip()
    if backend in ("none", "", "callable"):
        return None

    try:
        if backend == "http":
            endpoint = getattr(config.grounding, "vision_endpoint", None)
            if not endpoint:
                logger.warning(
                    "vision_backend=http but grounding.vision_endpoint is unset; vision tier dormant."
                )
                return None
            from bubblegum.core.vision.backends.http import HTTPGroundingProvider
            timeout_ms = getattr(config.grounding, "vision_endpoint_timeout_ms", 30_000)
            return HTTPGroundingProvider(endpoint=endpoint, timeout=max(timeout_ms, 1) / 1000.0)

        model = getattr(config.ai, "vision_model", None)
        if not model:
            logger.warning(
                "vision_backend=%s but ai.vision_model is unset; vision tier dormant.", backend
            )
            return None

        if backend == "anthropic":
            from bubblegum.core.vision.backends.anthropic import AnthropicVisionProvider
            return AnthropicVisionProvider(model=model, create_client=True)
        if backend == "openai":
            from bubblegum.core.vision.backends.openai import OpenAIVisionProvider
            return OpenAIVisionProvider(model=model, create_client=True)
    except Exception as exc:  # noqa: BLE001 — dormant tier must never crash a run
        logger.debug("Vision provider build failed; vision tier dormant: %s", exc)
        return None

    logger.warning("Unknown grounding.vision_backend=%r; vision tier dormant.", backend)
    return None
