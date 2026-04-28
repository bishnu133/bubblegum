"""
bubblegum/core/grounding/resolvers/memory_cache.py
===================================================
MemoryCacheResolver — Tier 1, priority 10, web + mobile, cost_level=low.

SQLite-backed cache that maps (screen_signature, step_hash) → ResolvedTarget.
All DB I/O is delegated to MemoryLayer (bubblegum/core/memory/layer.py).

Staleness checks are applied by MemoryLayer.lookup() before returning a result:
  1. screen_signature still matches exactly (it is the cache key — guaranteed)
  2. Last success was within TTL (default 7 days, configurable)
  3. failure_count < max_failures (default 3, configurable)

If any check fails: MemoryLayer returns None → resolve() returns [] and lets
downstream resolvers win.

required_context() returns ["screen_signature"] — the resolver is skipped via
can_run() when the signature is absent (UIContext.screen_signature not populated).

Write API (called by SDK after execution):
  record_success(intent, target)  — upsert winning resolution into DB
  record_failure(intent)          — increment failure_count for cached mapping

step_hash:
  Stable SHA-256 of instruction.lower() + channel + action_type (first 16 hex chars).
  Uniquely identifies *what the step does* independent of element location.

_get_conn():
  Passthrough to MemoryLayer._get_conn() — exposed for test introspection only.
  Allows unit tests to insert raw rows directly into SQLite to control timestamps
  and failure counts without going through the public write API.

Phase 3 — delegates to MemoryLayer; removes inline SQLite from Phase 1B.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.memory.layer import MemoryLayer
from bubblegum.core.schemas import ResolvedTarget, StepIntent

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS    = 7
_DEFAULT_MAX_FAILURES = 3


def _step_hash(intent: StepIntent) -> str:
    """Stable hash of instruction + channel + action_type (16 hex chars)."""
    key = f"{intent.instruction.lower().strip()}|{intent.channel}|{intent.action_type}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class MemoryCacheResolver(Resolver):
    """
    Screen-fingerprint + step-hash cache resolver backed by SQLite (via MemoryLayer).

    On a cache hit, MemoryLayer applies staleness checks (TTL, failure_count).
    Returns [] on miss or stale entry — never raises — so downstream resolvers
    can take over transparently.

    After successful execution the SDK calls record_success() to persist the
    mapping. record_failure() is called after ExecutionFailedError to age out
    a bad cached ref.
    """

    name:       str       = "memory_cache"
    priority:   int       = 10
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "low"
    tier:       int       = 1

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._layer = MemoryLayer(db_path=db_path)

    # ------------------------------------------------------------------
    # Resolver contract
    # ------------------------------------------------------------------

    def required_context(self) -> list[str]:
        return ["screen_signature"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        screen_sig = intent.context.get("screen_signature", "")
        if not screen_sig:
            return []

        ttl_days     = getattr(intent.options, "memory_ttl_days",    _DEFAULT_TTL_DAYS)
        max_failures = getattr(intent.options, "memory_max_failures", _DEFAULT_MAX_FAILURES)

        step_h = _step_hash(intent)
        entry  = self._layer.lookup(screen_sig, step_h, ttl_days, max_failures)

        if entry is None:
            return []

        logger.debug(
            "MemoryCache: HIT  sig=%r  hash=%s  ref=%r  conf=%.2f",
            screen_sig[:20], step_h, entry.ref, entry.confidence,
        )
        return [
            ResolvedTarget(
                ref=entry.ref,
                confidence=entry.confidence,
                resolver_name=self.name,
                metadata={**entry.metadata, "cached_from": entry.resolver_name},
            )
        ]

    # ------------------------------------------------------------------
    # Write API (called by SDK after execution)
    # ------------------------------------------------------------------

    def record_success(self, intent: StepIntent, target: ResolvedTarget) -> None:
        """
        Upsert a successful resolution into the cache.

        Call this after the adapter confirms execution succeeded.
        """
        screen_sig = intent.context.get("screen_signature", "")
        if not screen_sig:
            return

        step_h = _step_hash(intent)
        self._layer.record_success(
            screen_signature=screen_sig,
            step_hash=step_h,
            resolver_name=target.resolver_name,
            ref=target.ref,
            confidence=target.confidence,
            metadata=target.metadata,
        )

    def record_failure(self, intent: StepIntent) -> None:
        """
        Increment failure_count for a cached mapping.

        Call this when a cached ref fails on execution so the cache can be
        invalidated after max_failures consecutive failures.
        """
        screen_sig = intent.context.get("screen_signature", "")
        if not screen_sig:
            return

        step_h = _step_hash(intent)
        self._layer.record_failure(screen_sig, step_h)

    # ------------------------------------------------------------------
    # Test introspection helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """
        Return the underlying sqlite3.Connection from MemoryLayer.

        Exposed for unit test introspection only — allows tests to insert raw
        rows directly to control timestamps and failure counts without going
        through the public write API.

        Do NOT call this in production code.
        """
        return self._layer._get_conn()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying MemoryLayer connection."""
        self._layer.close()

    def __del__(self) -> None:
        self.close()