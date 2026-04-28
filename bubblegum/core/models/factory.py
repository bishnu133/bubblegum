"""
bubblegum/core/models/factory.py
=================================
get_provider() factory — returns the correct ModelProvider for a given BubblegumConfig.

Phase 2 — fully implemented for openai; stubs for anthropic and local.
"""

from __future__ import annotations

from bubblegum.core.models.base import ModelProvider


def get_provider(config) -> ModelProvider:
    """
    Instantiate and return the ModelProvider specified in BubblegumConfig.

    Raises:
        ProviderConfigError: if ai.enabled is False, ai.model is not set,
                             or ai.provider is unknown.
    """
    from bubblegum.core.grounding.errors import ProviderConfigError

    def _err(msg: str) -> ProviderConfigError:
        return ProviderConfigError(step="provider_factory", message=msg)

    if not config.ai.enabled:
        raise _err(
            "AI is disabled (ai.enabled=false in bubblegum.yaml). "
            "Set ai.enabled=true to use LLM resolvers."
        )

    provider_name: str       = (config.ai.provider or "").lower().strip()
    model:         str | None = config.ai.model

    if not model:
        raise _err(
            f"ai.model is not set in bubblegum.yaml. "
            f"Add 'model: <your-model-name>' under the 'ai:' section "
            f"(provider={provider_name!r})."
        )

    if provider_name == "openai":
        from bubblegum.core.models.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)

    if provider_name == "anthropic":
        from bubblegum.core.models.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)

    if provider_name in ("local", "ollama"):
        from bubblegum.core.models.local_provider import LocalProvider
        return LocalProvider(model=model)

    if provider_name == "gemini":
        raise _err(
            "Gemini provider is not yet implemented. "
            "Supported providers in Phase 2: openai, anthropic (stub), local (stub)."
        )

    raise _err(
        f"Unknown ai.provider: {provider_name!r}. "
        f"Supported values: openai, anthropic, gemini, local."
    )
