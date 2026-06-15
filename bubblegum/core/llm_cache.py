"""
bubblegum/core/llm_cache.py
===========================
LLM grounding decision cache (X2).

Identical screens shouldn't re-call the model. This is a process-global cache
of Tier-3 LLM grounding decisions keyed on screen signature + instruction +
action_type, so the *second* time a run encounters the same screen/step the
resolved targets replay with zero model calls. It is deliberately distinct from
the element memory cache (``core/memory``): that persists resolutions to disk
across runs; this is an in-process speed/cost optimization for repeat screens
within a run, reset per run.
"""

from __future__ import annotations

import re
import threading
from typing import List

from bubblegum.core.schemas import ResolvedTarget

_WS_RE = re.compile(r"\s+")
_lock = threading.Lock()
_CACHE: dict[str, list[ResolvedTarget]] = {}
_hits = 0
_misses = 0


def make_key(intent) -> str | None:
    """Build a cache key from screen signature + instruction + action_type.

    Returns None when there is no screen signature to key on (we only cache
    when we can scope the decision to a specific screen).
    """
    screen_sig = str(intent.context.get("screen_signature") or "").strip()
    if not screen_sig:
        return None
    phrase = _WS_RE.sub(" ", str(getattr(intent, "match_phrase", "") or "")).strip().lower()
    action = str(getattr(intent, "action_type", "") or "")
    return f"{screen_sig}\x1f{action}\x1f{phrase}"


def get(key: str | None) -> List[ResolvedTarget] | None:
    """Return cached targets (copies) for ``key``, or None on miss."""
    global _hits, _misses
    if not key:
        return None
    with _lock:
        cached = _CACHE.get(key)
        if cached is None:
            _misses += 1
            return None
        _hits += 1
        # Return copies so callers mutating metadata don't corrupt the cache.
        return [t.model_copy(deep=True) for t in cached]


def put(key: str | None, targets: List[ResolvedTarget]) -> None:
    """Store ``targets`` for ``key`` (no-op when key is None or targets empty)."""
    if not key or not targets:
        return
    with _lock:
        _CACHE[key] = [t.model_copy(deep=True) for t in targets]


def reset() -> None:
    """Clear the cache and stats — call at the start of a run."""
    global _hits, _misses
    with _lock:
        _CACHE.clear()
        _hits = 0
        _misses = 0


def stats() -> dict:
    """Return ``{hits, misses, size}`` (for diagnostics / tests)."""
    with _lock:
        return {"hits": _hits, "misses": _misses, "size": len(_CACHE)}
