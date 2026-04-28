"""
bubblegum/core/models/anthropic_provider.py
============================================
Anthropic implementation of ModelProvider — stub for Phase 2, full in Phase 6.

Phase 2: raises NotImplementedError so tests can assert the stub behaviour.
Phase 6: replace with real anthropic>=0.20 SDK calls.
"""

from __future__ import annotations

from bubblegum.core.models.base import CompletionResult, ModelProvider


class AnthropicProvider(ModelProvider):
    """
    ModelProvider backed by the Anthropic Messages API.

    Phase 2 stub — raises NotImplementedError.
    Full implementation deferred to Phase 6.

    Args:
        model:   Model name, e.g. "claude-sonnet-latest". Must be set explicitly.
        api_key: Optional API key. Falls back to ANTHROPIC_API_KEY env var.
    """

    provider_name: str = "anthropic"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        if not model:
            raise ValueError(
                "AnthropicProvider: 'model' must be set explicitly in bubblegum.yaml."
            )
        self.model = model
        self._api_key = api_key

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
    ) -> CompletionResult:
        raise NotImplementedError(
            "AnthropicProvider is a Phase 2 stub. "
            "Full implementation will be added in Phase 6."
        )
