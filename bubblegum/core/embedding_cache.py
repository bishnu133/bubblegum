"""
bubblegum/core/embedding_cache.py
=================================
Process-global embedding cache for the semantic Tier-2 resolver (Task #4).

Embeddings of a given string are deterministic, so the same element label /
target phrase never needs to be embedded twice in a process. This cache is keyed
on (model, text) and is safe to keep for the process lifetime — unlike the LLM
decision cache (screen decisions can change), so there is no per-run reset in
the hot path. reset() exists for test isolation.

Efficiency: embed_cached() batches every uncached string into a SINGLE provider
call, so a screen with N labels costs at most one round-trip the first time and
zero thereafter.
"""

from __future__ import annotations

import math
import threading

_lock = threading.Lock()
_CACHE: dict[str, list[float]] = {}
_hits = 0
_misses = 0

_SEP = "\x1f"


def _key(model: str, text: str) -> str:
    return f"{model}{_SEP}{text}"


def embed_cached(provider, texts: list[str]) -> list[list[float] | None]:
    """Return a vector per input text (order preserved), using the cache.

    Uncached texts are embedded in one batched provider.embed() call. On a
    provider error, the uncached entries come back as None so the caller can
    skip them rather than fail the whole resolution.
    """
    global _hits, _misses
    model = str(getattr(provider, "model", "?"))
    out: list[list[float] | None] = [None] * len(texts)

    missing_idx: list[int] = []
    missing_txt: list[str] = []
    with _lock:
        for i, t in enumerate(texts):
            cached = _CACHE.get(_key(model, t))
            if cached is None:
                _misses += 1
                missing_idx.append(i)
                missing_txt.append(t)
            else:
                _hits += 1
                out[i] = cached

    if not missing_txt:
        return out

    # Provider call happens OUTSIDE the lock so a slow network round-trip does
    # not serialize other threads.
    vectors = provider.embed(missing_txt)

    with _lock:
        for j, t in enumerate(missing_txt):
            if j < len(vectors) and vectors[j]:
                vec = [float(x) for x in vectors[j]]
                _CACHE[_key(model, t)] = vec
                out[missing_idx[j]] = vec
    return out


def cosine(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity in [-1, 1]; 0.0 for empty / mismatched / zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def reset() -> None:
    """Clear the cache and stats (test isolation)."""
    global _hits, _misses
    with _lock:
        _CACHE.clear()
        _hits = 0
        _misses = 0


def stats() -> dict:
    with _lock:
        return {"hits": _hits, "misses": _misses, "size": len(_CACHE)}
