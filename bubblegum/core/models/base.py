"""
bubblegum/core/models/base.py
==============================
ModelProvider ABC — contract for every LLM provider implementation.

All providers must implement async complete() and return a plain string.
Logging of safe metadata (provider, model, token counts, latency) is the
responsibility of each concrete provider — raw prompts must NEVER be logged.

Phase 2 — locked contract.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CompletionResult:
    """
    Structured result from a model completion call.

    Attributes:
        text:           Raw model response text.
        input_tokens:   Token count for the prompt (0 if provider does not report).
        output_tokens:  Token count for the completion (0 if provider does not report).
        latency_ms:     Wall-clock time for the API call in milliseconds.
        provider:       Provider name (e.g. "openai", "anthropic").
        model:          Model name used for the call.
    """
    text:          str
    input_tokens:  int   = 0
    output_tokens: int   = 0
    latency_ms:    int   = 0
    provider:      str   = ""
    model:         str   = ""


class ModelProvider(ABC):
    """
    Abstract base for all Bubblegum LLM provider implementations.

    Contract:
      - async complete() is the only required method.
      - Providers MUST log safe metadata (see _log_call).
      - Providers MUST NOT log raw prompt text or screenshot bytes.
      - Structured JSON responses are requested via response_format="json".
    """

    # Subclasses declare their provider name and model as class attributes
    # or set them in __init__ from config.
    provider_name: str = "base"
    model: str = ""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,   # "json" requests JSON-mode output
    ) -> CompletionResult:
        """
        Send a completion request to the model and return a CompletionResult.

        Args:
            prompt:          User-turn content. NEVER logged in raw form.
            system:          System prompt. NEVER logged in raw form.
            response_format: Pass "json" to request structured JSON output.

        Returns:
            CompletionResult with response text and safe metadata.

        Raises:
            ProviderConfigError: if the provider is not configured.
            Any provider-specific network/API error (caller handles).
        """
        ...

    # ------------------------------------------------------------------
    # Safe metadata logging — shared helper, always call from complete()
    # ------------------------------------------------------------------

    def _log_call(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        payload_type: str = "text",
        redacted: bool = True,
    ) -> None:
        """
        Log safe call metadata. NEVER logs raw prompt content or screenshots.

        This method is intentionally NOT abstract — providers call it from
        within their complete() implementation after the API response arrives.

        Logged fields (safe):
          provider, model, payload_type, input_tokens, output_tokens,
          latency_ms, redacted

        NOT logged:
          prompt text, system prompt, screenshot bytes, DOM snapshots
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "provider_call provider=%s model=%s payload_type=%s "
            "input_tokens=%d output_tokens=%d latency_ms=%d redacted=%s",
            self.provider_name,
            self.model,
            payload_type,
            input_tokens,
            output_tokens,
            latency_ms,
            redacted,
        )
