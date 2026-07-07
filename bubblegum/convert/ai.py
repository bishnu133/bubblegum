"""
bubblegum/convert/ai.py
=======================
Optional AI fallback for step normalization.

Provider-agnostic by construction: it reuses Bubblegum's existing
``ModelProvider`` factory (``get_provider``) and the tiny ``llm_decompose``
prompt, so whatever provider a team configures (anthropic / openai / gemini /
local-ollama) works with zero converter-side changes.

Posture:
  * Off unless ``convert.ai.enabled`` (or a passed override) is true.
  * Only ever sees the short step *text* — never DOM, never screenshots.
  * Fails safe: any error returns None so the deterministic parse stands.

``build_ai_hook`` returns a ``(text, section) -> ParsedIntent | None`` callable
that ``normalize`` consults only for steps the rule-based grammar could not
confidently split.
"""

from __future__ import annotations

import asyncio
import logging

from bubblegum.convert.profile import ConvertProfile
from bubblegum.core.parser.instruction import ParsedIntent

logger = logging.getLogger(__name__)


def build_ai_hook(profile: ConvertProfile, config=None):
    """Return an ai_hook callable, or None when AI is disabled/unavailable.

    Args:
        profile: the ConvertProfile (reads convert.ai.*).
        config:  an optional BubblegumConfig; when omitted it is loaded and the
                 converter's provider/model overrides are applied on top.
    """
    if not profile.ai.enabled:
        return None

    try:
        from bubblegum.core.config import BubblegumConfig
        from bubblegum.core.models.factory import get_provider

        cfg = config or BubblegumConfig.load()
        # Converter-specific overrides win over the runtime ai: block so a team
        # can use a stronger authoring model than their runtime resolver model.
        if profile.ai.provider:
            cfg.ai.provider = profile.ai.provider
        if profile.ai.model:
            cfg.ai.model = profile.ai.model
        cfg.ai.enabled = True
        provider = get_provider(cfg)
    except Exception as exc:  # noqa: BLE001 - AI is strictly optional
        logger.warning("convert AI fallback disabled (provider setup failed): %s", exc)
        return None

    from bubblegum.core.parser.llm_decompose import llm_decompose

    def _hook(text: str, section: str) -> ParsedIntent | None:
        try:
            result = asyncio.run(llm_decompose(text, provider))
        except Exception as exc:  # noqa: BLE001 - fallback must never raise
            logger.warning("convert AI decompose failed for step; keeping deterministic parse: %s", exc)
            return None
        if result is None or result.action_type is None:
            return None
        return ParsedIntent(
            action_type=result.action_type,
            target_phrase=result.target_phrase,
            input_value=result.input_value,
            confident=bool(result.target_phrase),
        )

    return _hook
