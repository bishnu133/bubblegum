"""
bubblegum/core/models/embeddings.py
====================================
Embedding providers for the semantic Tier-2 resolver (Task #4).

An EmbeddingProvider turns short UI strings (a target phrase, element labels)
into vectors so the SemanticResolver can match on *meaning* — catching label
drift like "Submit" -> "Continue" that edit-distance fuzzy matching misses.

Design (mirrors the ModelProvider seam):
  * Providers are pluggable and injected, never created behind the caller's
    back — the tier is dormant until one is wired.
  * embed() is synchronous — the grounding engine runs resolvers synchronously,
    and a sync embeddings call avoids the event-loop gymnastics the LLM tier
    needs. Batching keeps it efficient (one API round-trip for all labels).
  * Only OpenAI has a first-party embeddings backend here. Other providers
    (offline sentence-transformers, self-hosted, Voyage, etc.) are supported via
    configure_embedding_provider() with a callable — no heavy ML dependency is
    imposed on the base package.
  * All failures are the caller's to handle; the SemanticResolver treats any
    embedding error as "no semantic candidates" and defers to the LLM tier.
"""

from __future__ import annotations

import logging
from typing import Callable, Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Contract: embed a batch of strings into equal-length float vectors."""

    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input string, in the same order."""
        ...


class OpenAIEmbeddingProvider:
    """EmbeddingProvider backed by the OpenAI embeddings API (sync client).

    Args:
        model:      e.g. "text-embedding-3-small". Must be set explicitly.
        api_key:    Optional; falls back to OPENAI_API_KEY.
        dimensions: Optional output dimensionality (text-embedding-3-* support
                    shortening for cheaper storage/compute).
    """

    provider_name = "openai"

    def __init__(self, model: str, api_key: str | None = None, dimensions: int | None = None) -> None:
        if not model:
            raise ValueError("OpenAIEmbeddingProvider: 'model' must be set explicitly.")
        self.model = model
        self._api_key = api_key
        self._dimensions = dimensions
        self._client: object | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        client = self._get_client()
        kwargs: dict = {"model": self.model, "input": items}
        if self._dimensions:
            kwargs["dimensions"] = int(self._dimensions)
        resp = client.embeddings.create(**kwargs)
        # Best-effort cost accounting so the per-run budget still bounds spend.
        try:
            from bubblegum.core import cost
            usage = getattr(resp, "usage", None)
            total = getattr(usage, "total_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
            cost.record_usage(self.model, total, 0)
        except Exception:  # noqa: BLE001 — accounting must never break resolution
            pass
        # Preserve input order (the API guarantees data[i] matches input[i]).
        ordered = sorted(resp.data, key=lambda d: getattr(d, "index", 0))
        return [list(getattr(d, "embedding", []) or []) for d in ordered]

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "openai>=1.0 is required for OpenAIEmbeddingProvider. "
                    "Install with: pip install openai"
                ) from exc
            kwargs = {}
            if self._api_key is not None:
                kwargs["api_key"] = self._api_key
            self._client = OpenAI(**kwargs)
        return self._client


class CallableEmbeddingProvider:
    """Wrap any ``fn(list[str]) -> list[vector]`` as an EmbeddingProvider.

    The escape hatch for offline / self-hosted embeddings (e.g.
    sentence-transformers) without adding a heavy dependency to Bubblegum:

        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer("all-MiniLM-L6-v2")
        configure_embedding_provider(lambda texts: m.encode(texts).tolist())
    """

    provider_name = "callable"

    def __init__(self, fn: Callable[[list[str]], Sequence[Sequence[float]]], model: str = "callable") -> None:
        if not callable(fn):
            raise TypeError("CallableEmbeddingProvider requires a callable fn(list[str]) -> vectors.")
        self._fn = fn
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        vectors = self._fn(items)
        return [[float(x) for x in vec] for vec in vectors]


def get_embedding_provider(config) -> EmbeddingProvider | None:
    """Build the configured embedding provider, or None when unavailable.

    Returns None (dormant tier) when AI is disabled, no embedding_model is set,
    or the provider has no built-in embeddings backend. Never raises.
    """
    if not getattr(config.ai, "enabled", False):
        return None
    model = getattr(config.ai, "embedding_model", None)
    if not model:
        return None
    provider = (getattr(config.ai, "embedding_provider", None) or config.ai.provider or "").lower().strip()
    try:
        if provider == "openai":
            return OpenAIEmbeddingProvider(model=model)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Embedding provider build failed; semantic tier dormant: %s", exc)
        return None
    logger.debug(
        "No built-in embeddings backend for provider=%r; inject one via "
        "configure_embedding_provider() to enable the semantic tier.",
        provider,
    )
    return None
