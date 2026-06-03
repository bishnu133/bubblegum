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

from bubblegum.core.models.base import CompletionResult, ModelProvider

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

    def __init__(self, model: str, api_key: str | None = None) -> None:
        if not model:
            raise ValueError(
                "AnthropicProvider: 'model' must be set explicitly in bubblegum.yaml."
            )
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
    ) -> CompletionResult:
        """
        Send a completion request to the Anthropic Messages API.

        Args:
            prompt:          User-turn content. Never logged in raw form.
            system:          System prompt. Never logged in raw form.
            response_format: Pass "json" to request structured JSON output.

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
        if response_format == "json":
            system_prompt = (system_prompt + _JSON_SUFFIX).strip()

        t0 = time.monotonic()

        client = _anthropic.AsyncAnthropic(api_key=self._api_key)
        kwargs: dict = dict(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await client.messages.create(**kwargs)

        latency_ms = int((time.monotonic() - t0) * 1000)
        raw_text = _extract_text(response)

        if response_format == "json":
            raw_text = _strip_code_fence(raw_text)

        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)

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


def _strip_code_fence(raw: str) -> str:
    """Remove markdown code fences that some models wrap JSON in."""
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence (```json or ```) and closing fence (```)
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        return "\n".join(inner).strip()
    return stripped
