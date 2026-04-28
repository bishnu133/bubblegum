"""
bubblegum/core/memory/layer.py
================================
MemoryLayer — SQLite-backed persistence for the resolver cache.

This module is the canonical read/write interface for Bubblegum's memory.
MemoryCacheResolver delegates all DB I/O to this layer; it no longer manages
its own connection.

Public API
----------
layer = MemoryLayer()                            # default: .bubblegum/memory.db
layer = MemoryLayer(db_path=Path("/tmp/test.db"))

layer.record_success(screen_signature, step_hash, resolver_name, ref, confidence)
layer.record_failure(screen_signature, step_hash)
entry = layer.lookup(screen_signature, step_hash, ttl_days, max_failures)
  → CacheEntry | None

CacheEntry fields
-----------------
  ref           str    — resolved locator / element ref
  confidence    float  — confidence at time of last successful resolution
  resolver_name str    — which resolver produced the winning ref
  metadata      dict   — arbitrary metadata blob (JSON-serialised)

Staleness checks inside lookup()
---------------------------------
  1. TTL: last_success older than ttl_days          → return None
  2. Failures: failure_count >= max_failures         → return None
  3. Key miss: (screen_sig, step_hash) not in DB    → return None

All three conditions are tested in lookup() so MemoryCacheResolver stays thin.

Thread safety
-------------
Connection is opened once per MemoryLayer instance with check_same_thread=False.
Safe for single-threaded async use (asyncio) and for simple multi-threaded test
runners. Not safe for concurrent writes from multiple processes — use a shared
in-process singleton when CI parallelism matters (Phase 5 concern).

Phase 3.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH  = Path(".bubblegum") / "memory.db"
_DEFAULT_TTL_DAYS = 7
_DEFAULT_MAX_FAIL = 3

_DDL = """
CREATE TABLE IF NOT EXISTS bubblegum_memory (
    screen_sig    TEXT    NOT NULL,
    step_hash     TEXT    NOT NULL,
    ref           TEXT    NOT NULL,
    confidence    REAL    NOT NULL,
    resolver_name TEXT    NOT NULL,
    metadata_json TEXT    NOT NULL DEFAULT '{}',
    last_success  TEXT    NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 1,
    failure_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (screen_sig, step_hash)
);
"""


@dataclass
class CacheEntry:
    """A successful resolution retrieved from the MemoryLayer."""

    ref:           str
    confidence:    float
    resolver_name: str
    metadata:      dict = field(default_factory=dict)


class MemoryLayer:
    """
    SQLite-backed key-value store for (screen_sig, step_hash) → CacheEntry.

    Instantiate once per process (or pass a custom db_path for testing).
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def record_success(
        self,
        screen_signature: str,
        step_hash: str,
        resolver_name: str,
        ref: str,
        confidence: float,
        metadata: dict | None = None,
    ) -> None:
        """
        Upsert a successful resolution.

        On conflict: updates ref/confidence/resolver/metadata/last_success,
        increments success_count, resets failure_count to 0.
        """
        now_iso   = datetime.now(tz=timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        try:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO bubblegum_memory
                    (screen_sig, step_hash, ref, confidence, resolver_name,
                     metadata_json, last_success, success_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)
                ON CONFLICT(screen_sig, step_hash) DO UPDATE SET
                    ref           = excluded.ref,
                    confidence    = excluded.confidence,
                    resolver_name = excluded.resolver_name,
                    metadata_json = excluded.metadata_json,
                    last_success  = excluded.last_success,
                    success_count = bubblegum_memory.success_count + 1,
                    failure_count = 0
                """,
                (screen_signature, step_hash, ref, confidence, resolver_name,
                 meta_json, now_iso),
            )
            conn.commit()
            logger.debug(
                "MemoryLayer: recorded success  sig=%r  hash=%s  ref=%r  conf=%.2f",
                screen_signature[:20], step_hash, ref, confidence,
            )
        except Exception as exc:
            logger.warning("MemoryLayer.record_success failed: %s", exc)

    def record_failure(self, screen_signature: str, step_hash: str) -> None:
        """
        Increment failure_count for an existing cache entry.

        If no entry exists, this is a no-op (we only track failures for
        previously successful mappings).
        """
        try:
            conn = self._get_conn()
            conn.execute(
                """
                UPDATE bubblegum_memory
                SET failure_count = failure_count + 1
                WHERE screen_sig = ? AND step_hash = ?
                """,
                (screen_signature, step_hash),
            )
            conn.commit()
            logger.debug(
                "MemoryLayer: recorded failure  sig=%r  hash=%s",
                screen_signature[:20], step_hash,
            )
        except Exception as exc:
            logger.warning("MemoryLayer.record_failure failed: %s", exc)

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def lookup(
        self,
        screen_signature: str,
        step_hash: str,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        max_failures: int = _DEFAULT_MAX_FAIL,
    ) -> CacheEntry | None:
        """
        Retrieve a cached entry, applying staleness checks.

        Staleness checks (any failure → return None):
          1. Entry not found (miss)
          2. last_success older than ttl_days
          3. failure_count >= max_failures

        Returns:
            CacheEntry on a valid hit, None otherwise.
        """
        try:
            row = self._fetch(screen_signature, step_hash)
        except Exception as exc:
            logger.warning("MemoryLayer.lookup: DB read error: %s", exc)
            return None

        if row is None:
            logger.debug(
                "MemoryLayer: miss  sig=%r  hash=%s", screen_signature[:20], step_hash
            )
            return None

        ref, confidence, resolver_name, metadata_json, last_success_str, failure_count = row

        # Staleness check 1 — TTL
        try:
            last_success = datetime.fromisoformat(last_success_str)
            age = datetime.now(tz=timezone.utc) - last_success
            if age > timedelta(days=ttl_days):
                logger.debug(
                    "MemoryLayer: TTL expired (age=%s, ttl=%dd)  sig=%r",
                    age, ttl_days, screen_signature[:20],
                )
                return None
        except Exception as exc:
            logger.warning("MemoryLayer: TTL parse error: %s", exc)
            return None

        # Staleness check 2 — failure_count
        if failure_count >= max_failures:
            logger.debug(
                "MemoryLayer: max failures reached (%d >= %d)  sig=%r",
                failure_count, max_failures, screen_signature[:20],
            )
            return None

        # Valid hit
        try:
            metadata: dict = json.loads(metadata_json)
        except Exception:
            metadata = {}

        logger.debug(
            "MemoryLayer: HIT  sig=%r  hash=%s  ref=%r  conf=%.2f",
            screen_signature[:20], step_hash, ref, confidence,
        )
        return CacheEntry(
            ref=ref,
            confidence=confidence,
            resolver_name=resolver_name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __del__(self) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute(_DDL)
            self._conn.commit()
        return self._conn

    def _fetch(self, screen_sig: str, step_hash: str):
        """
        Return raw DB row or None.

        Columns: ref, confidence, resolver_name, metadata_json,
                 last_success, failure_count
        """
        conn   = self._get_conn()
        cursor = conn.execute(
            """
            SELECT ref, confidence, resolver_name, metadata_json,
                   last_success, failure_count
            FROM bubblegum_memory
            WHERE screen_sig = ? AND step_hash = ?
            """,
            (screen_sig, step_hash),
        )
        return cursor.fetchone()
