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


def _is_schema_unsupported(exc: Exception) -> bool:
    """Heuristic: did the API reject the request because of json_schema support?

    Used to decide whether to retry once in json_object mode. Matches on the
    error text so it works without importing openai's error classes.
    """
    msg = str(getattr(exc, "message", "") or exc).lower()
    return any(
        token in msg
        for token in ("json_schema", "response_format", "structured output", "not supported", "unsupported")
    )


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
        *,
        max_tokens: int | None = None,
        prompt_caching: bool = True,
    ) -> None:
        if not model:
            raise ValueError(
                "OpenAIProvider: 'model' must be set explicitly. "
                "Add 'ai.model: <your-model-name>' to bubblegum.yaml."
            )
        self.model = model
        self._api_key = api_key     # None → SDK reads OPENAI_API_KEY env var
        self._log_calls = log_calls
        self._max_tokens = max_tokens
        # OpenAI applies prompt caching automatically for long, repeated
        # prefixes — there is no request flag to set. The parameter is accepted
        # for provider-agnostic parity and is intentionally a no-op here.
        self._prompt_caching = bool(prompt_caching)
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
        json_schema: dict | None = None,
    ) -> CompletionResult:
        """
        Call the OpenAI Chat Completions API.

        Args:
            prompt:          User-turn content. NEVER logged.
            system:          System prompt. NEVER logged.
            response_format: Pass "json" to enable json_object mode.
            json_schema:     Optional normalized schema (name/description/schema)
                             for Structured Outputs (strict json_schema mode).

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
        if self._max_tokens is not None:
            kwargs["max_tokens"] = int(self._max_tokens)
        if json_schema is not None:
            # Structured Outputs: the model is constrained to emit JSON matching
            # the schema — no fence-stripping, no unparseable output.
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("name", "response"),
                    "schema": json_schema.get("schema", {}),
                    "strict": True,
                },
            }
        elif response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            # A model/endpoint that rejects strict json_schema falls back once to
            # json_object mode so structured output never hard-fails a run.
            if json_schema is not None and _is_schema_unsupported(exc):
                logger.warning(
                    "OpenAI json_schema unsupported (model=%s); falling back to json_object",
                    self.model,
                )
                kwargs["response_format"] = {"type": "json_object"}
                response = await client.chat.completions.create(**kwargs)
            else:
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

    def _get_client(self):  # noqa: D401
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
