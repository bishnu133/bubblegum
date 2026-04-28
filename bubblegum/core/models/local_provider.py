"""
bubblegum/core/models/local_provider.py
========================================
Local (Ollama) implementation of ModelProvider — stub for Phase 2, full in Phase 6.

Communicates with Ollama via its HTTP API (http://localhost:11434 by default).

Phase 2: raises NotImplementedError.
Phase 6: full implementation via httpx async HTTP calls to Ollama /api/chat endpoint.
"""

from __future__ import annotations

from bubblegum.core.models.base import CompletionResult, ModelProvider


class LocalProvider(ModelProvider):
    """
    ModelProvider backed by a local Ollama server.

    Phase 2 stub — raises NotImplementedError.
    Full implementation deferred to Phase 6.

    Args:
        model:    Model name, e.g. "llama3", "mistral". Must be set explicitly.
        base_url: Ollama server base URL. Default: http://localhost:11434
    """

    provider_name: str = "local"

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
    ) -> None:
        if not model:
            raise ValueError(
                "LocalProvider: 'model' must be set explicitly in bubblegum.yaml."
            )
        self.model = model
        self._base_url = base_url

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_format: str | None = None,
    ) -> CompletionResult:
        raise NotImplementedError(
            "LocalProvider (Ollama) is a Phase 2 stub. "
            "Full implementation will be added in Phase 6."
        )
