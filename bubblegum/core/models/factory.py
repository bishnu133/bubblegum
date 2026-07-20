"""
bubblegum/core/models/factory.py
=================================
get_provider() factory — returns the correct ModelProvider for a given BubblegumConfig.

Phase 2 — fully implemented for openai; stubs for anthropic and local.
"""

from __future__ import annotations

from bubblegum.core.models.base import ModelProvider


def get_provider(config, role: str = "default") -> ModelProvider:
    """
    Instantiate and return the ModelProvider specified in BubblegumConfig.

    Args:
        config: BubblegumConfig instance.
        role:   Which model to build — "fast" (grounding/decompose; uses
                ai.fast_model, else ai.model), "strong" (escalation; uses
                ai.strong_model, else ai.model), or "default" (ai.model).
                Fast/strong fall back to the base model so single-model configs
                are unchanged.

    Raises:
        ProviderConfigError: if ai.enabled is False, the resolved model is not
                             set, or ai.provider is unknown.
    """
    from bubblegum.core.grounding.errors import ProviderConfigError

    def _err(msg: str) -> ProviderConfigError:
        return ProviderConfigError(step="provider_factory", message=msg)

    if not config.ai.enabled:
        raise _err(
            "AI is disabled (ai.enabled=false in bubblegum.yaml). "
            "Set ai.enabled=true to use LLM resolvers."
        )

    provider_name: str = (config.ai.provider or "").lower().strip()

    if role == "fast":
        model = config.ai.resolved_fast_model()
    elif role == "strong":
        model = config.ai.resolved_strong_model()
    else:
        model = config.ai.model

    if not model:
        raise _err(
            f"ai.model is not set in bubblegum.yaml. "
            f"Add 'model: <your-model-name>' under the 'ai:' section "
            f"(provider={provider_name!r}, role={role!r})."
        )

    # Shared call-tuning knobs applied to every real provider.
    tuning = {
        "max_tokens": config.ai.max_tokens,
        "prompt_caching": config.ai.prompt_caching,
    }

    if provider_name == "openai":
        from bubblegum.core.models.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model, **tuning)

    if provider_name == "anthropic":
        from bubblegum.core.models.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model, **tuning)

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
