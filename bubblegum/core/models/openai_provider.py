"""
bubblegum/core/models/openai_provider.py
=========================================
OpenAI implementation of ModelProvider.

Uses openai>=1.0 async client. Model is read from config — no hardcoded default.
Structured JSON output is requested via response_format={"type": "json_object"}.

Logging:
  - Logs: provider name, model, token counts, latency, payload type, redaction status.
  - Never logs: raw prompt text, system prompt, screenshot bytes, DOM content.

Phase 2 — fully implemented.
"""

from __future__ import annotations

import time
import logging

from bubblegum.core.models.base import CompletionResult, ModelProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(ModelProvider):
    """
    ModelProvider backed by the OpenAI Chat Completions API (openai>=1.0).

    Args:
        model:      Model name, e.g. "gpt-4o-mini". Read from config — never hardcoded.
        api_key:    Optional API key. Falls back to OPENAI_API_KEY env var if not set.
        log_calls:  Whether to emit safe metadata logs after each call (default True).
    """

    provider_name: str = "openai"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        log_calls: bool = True,
    ) -> None:
        if not model:
            raise ValueError(
                "OpenAIProvider: 'model' must be set explicitly. "
                "Add 'ai.model: <your-model-name>' to bubblegum.yaml."
            )
        self.model = model
        self._api_key = api_key     # None → SDK reads OPENAI_API_KEY env var
        self._log_calls = log_calls
        self._client: object | None = None  # lazy init to avoid import-time side effects

    # ------------------------------------------------------------------
    # ModelProvider contract
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
    ) -> CompletionResult:
        """
        Call the OpenAI Chat Completions API.

        Args:
            prompt:          User-turn content. NEVER logged.
            system:          System prompt. NEVER logged.
            response_format: Pass "json" to enable json_object mode.

        Returns:
            CompletionResult with text, token counts, and latency.
        """
        client = self._get_client()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model":    self.model,
            "messages": messages,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception:
            logger.error(
                "OpenAI API call failed provider=%s model=%s",
                self.provider_name,
                self.model,
            )
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)

        text          = response.choices[0].message.content or ""
        input_tokens  = response.usage.prompt_tokens     if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        if self._log_calls:
            self._log_call(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                payload_type="text+json" if response_format == "json" else "text",
                redacted=True,   # raw prompt is never sent to logger
            )

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider=self.provider_name,
            model=self.model,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_client(self):
        """Lazy-init the AsyncOpenAI client so import errors surface at call time."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "openai>=1.0 is required for OpenAIProvider. "
                    "Install with: pip install openai"
                ) from exc

            kwargs = {}
            if self._api_key is not None:
                kwargs["api_key"] = self._api_key

            self._client = AsyncOpenAI(**kwargs)

        return self._client
