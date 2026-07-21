"""
bubblegum/core/models/anthropic_provider.py
============================================
Anthropic Messages API implementation of ModelProvider.

Requires: pip install anthropic
API key:  ANTHROPIC_API_KEY environment variable (or pass api_key= directly)

Supported models (as of 2026):
  claude-haiku-4-5-20251001   — fastest, cheapest, good for UI grounding
  claude-sonnet-4-6            — best reasoning, higher cost
  claude-opus-4-8              — most capable

JSON mode: Anthropic has no native JSON mode. When response_format="json" is
requested we append a short JSON instruction to the system prompt and strip
any markdown code fences from the response before returning.
"""

from __future__ import annotations

import json
import logging
import os
import time

from bubblegum.core.models._shared import strip_code_fence as _strip_code_fence
from bubblegum.core.models.base import CompletionResult, ModelProvider
from bubblegum.core.models.resilience import call_with_resilience

logger = logging.getLogger(__name__)

_JSON_SUFFIX = "\n\nRespond with ONLY a valid JSON object. No markdown, no prose."


class AnthropicProvider(ModelProvider):
    """
    ModelProvider backed by the Anthropic Messages API.

    Args:
        model:   Model name, e.g. "claude-haiku-4-5-20251001". Must be set explicitly.
        api_key: Optional API key. Falls back to ANTHROPIC_API_KEY env var.
    """

    provider_name: str = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        *,
        max_tokens: int = 1024,
        prompt_caching: bool = True,
        timeout_ms: int = 30_000,
        max_retries: int = 2,
        retry_backoff_ms: int = 500,
    ) -> None:
        if not model:
            raise ValueError(
                "AnthropicProvider: 'model' must be set explicitly in bubblegum.yaml."
            )
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._max_tokens = int(max_tokens)
        self._prompt_caching = bool(prompt_caching)
        self._timeout_s = max(int(timeout_ms), 0) / 1000.0
        self._max_retries = max(int(max_retries), 0)
        self._backoff_ms = max(int(retry_backoff_ms), 0)
        self._client = None  # reused across calls (built lazily)

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
        json_schema: dict | None = None,
    ) -> CompletionResult:
        """
        Send a completion request to the Anthropic Messages API.

        Args:
            prompt:          User-turn content. Never logged in raw form.
            system:          System prompt. Never logged in raw form.
            response_format: Pass "json" to request structured JSON output.
            json_schema:     Optional normalized schema (name/description/schema).
                             When supplied, a single tool is defined with that
                             input_schema and tool_choice forces it, so the
                             model returns arguments guaranteed to match the
                             schema; the tool input is serialized into .text.

        Returns:
            CompletionResult with response text and safe metadata.

        Raises:
            ProviderConfigError: if anthropic SDK is not installed or API key missing.
            Any anthropic API error is re-raised for the caller to handle.
        """
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            from bubblegum.core.grounding.errors import ProviderConfigError
            raise ProviderConfigError(
                step="anthropic_provider",
                message=(
                    "The 'anthropic' package is not installed. "
                    "Run: pip install anthropic"
                ),
            ) from exc

        if not self._api_key:
            from bubblegum.core.grounding.errors import ProviderConfigError
            raise ProviderConfigError(
                step="anthropic_provider",
                message=(
                    "ANTHROPIC_API_KEY environment variable is not set. "
                    "Set it or pass api_key= to AnthropicProvider."
                ),
            )

        system_prompt = system or ""
        # With tool-use the schema is enforced by the tool, so the "reply in
        # JSON" nudge is only needed for the plain json path.
        if response_format == "json" and json_schema is None:
            system_prompt = (system_prompt + _JSON_SUFFIX).strip()

        t0 = time.monotonic()

        # Reuse a single AsyncAnthropic client across calls — avoids rebuilding
        # the client (and its connection pool) on every grounding request.
        if self._client is None:
            self._client = _anthropic.AsyncAnthropic(api_key=self._api_key)
        client = self._client

        kwargs: dict = dict(
            model=self.model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if json_schema is not None:
            tool_name = json_schema.get("name", "response")
            kwargs["tools"] = [
                {
                    "name": tool_name,
                    "description": json_schema.get("description", "Structured response."),
                    "input_schema": json_schema.get("schema", {}),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
        if system_prompt:
            # Prompt caching: the system prompt is stable across steps (the
            # grounding contract), so marking it cacheable lets Anthropic serve
            # the prefix from cache — big latency/cost win on repeat calls.
            # Falls back to a plain string when caching is disabled.
            if self._prompt_caching:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                kwargs["system"] = system_prompt

        response = await call_with_resilience(
            lambda: client.messages.create(**kwargs),
            timeout_s=self._timeout_s,
            max_retries=self._max_retries,
            backoff_ms=self._backoff_ms,
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        if json_schema is not None:
            # Prefer the forced tool's structured input; fall back to text if the
            # model somehow answered without calling the tool.
            tool_input = _extract_tool_input(response)
            if tool_input is not None:
                raw_text = json.dumps(tool_input)
            else:
                raw_text = _strip_code_fence(_extract_text(response))
        else:
            raw_text = _extract_text(response)
            if response_format == "json":
                raw_text = _strip_code_fence(raw_text)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        # Cache read/creation tokens (when caching is active) are logged for
        # observability but not billed as fresh input by the cost estimator.
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        if cache_read:
            logger.info(
                "provider_cache provider=%s model=%s cache_read_input_tokens=%d",
                self.provider_name, self.model, cache_read,
            )

        self._log_call(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            payload_type="json" if response_format == "json" else "text",
        )

        return CompletionResult(
            text=raw_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            provider=self.provider_name,
            model=self.model,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(response) -> str:
    """Pull text from the first text content block in a Messages response."""
    content = getattr(response, "content", []) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text or ""
    return ""


def _extract_tool_input(response) -> dict | None:
    """Return the input dict of the first tool_use block, or None if absent."""
    content = getattr(response, "content", []) or []
    for block in content:
        btype = getattr(block, "type", None)
        if btype == "tool_use":
            data = getattr(block, "input", None)
            if isinstance(data, dict):
                return data
        elif isinstance(block, dict) and block.get("type") == "tool_use":
            data = block.get("input")
            if isinstance(data, dict):
                return data
    return None


# strip_code_fence now lives in bubblegum.core.models._shared (single source),
# imported above as _strip_code_fence.
