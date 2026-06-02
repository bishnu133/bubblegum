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
    # CI cache export / import
    # ------------------------------------------------------------------

    def export(self, path: Path | str) -> int:
        """Export all cache entries to a portable JSON file.

        Returns the number of entries exported.
        The JSON file is human-readable, diffable, and safe to commit as a
        CI artifact or store in an S3/GCS bucket between runs.

        Format:
            {
              "version": 1,
              "exported_at": "<ISO-8601>",
              "entries": [...]
            }
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT screen_sig, step_hash, ref, confidence, resolver_name,
                   metadata_json, last_success, success_count, failure_count
            FROM bubblegum_memory
            ORDER BY last_success DESC
            """
        )
        rows = cursor.fetchall()

        entries = []
        for row in rows:
            (screen_sig, step_hash, ref, confidence, resolver_name,
             metadata_json, last_success, success_count, failure_count) = row
            try:
                metadata = json.loads(metadata_json)
            except Exception:
                metadata = {}
            entries.append({
                "screen_signature": screen_sig,
                "step_hash": step_hash,
                "ref": ref,
                "confidence": confidence,
                "resolver_name": resolver_name,
                "metadata": metadata,
                "last_success": last_success,
                "success_count": success_count,
                "failure_count": failure_count,
            })

        payload = {
            "version": 1,
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
            "entries": entries,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("MemoryLayer: exported %d entries to %s", len(entries), path)
        return len(entries)

    def import_from(self, path: Path | str, *, merge: bool = True) -> int:
        """Import cache entries from a JSON file previously produced by export().

        Args:
            path:  Path to the JSON cache file.
            merge: When True (default), existing entries are kept if they have
                   a higher success_count than the incoming entry. When False,
                   incoming entries always overwrite existing ones.

        Returns:
            Number of entries imported (new or updated).
        """
        path = Path(path)
        if not path.exists():
            logger.warning("MemoryLayer.import_from: file not found: %s", path)
            return 0

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("MemoryLayer.import_from: failed to parse %s: %s", path, exc)
            return 0

        if payload.get("version") != 1:
            logger.warning(
                "MemoryLayer.import_from: unknown version %r in %s", payload.get("version"), path
            )
            return 0

        entries = payload.get("entries", [])
        conn = self._get_conn()
        imported = 0

        for entry in entries:
            try:
                screen_sig    = entry["screen_signature"]
                step_hash     = entry["step_hash"]
                ref           = entry["ref"]
                confidence    = float(entry["confidence"])
                resolver_name = entry["resolver_name"]
                metadata_json = json.dumps(entry.get("metadata") or {})
                last_success  = entry.get("last_success", datetime.now(tz=timezone.utc).isoformat())
                success_count = int(entry.get("success_count", 1))
                failure_count = int(entry.get("failure_count", 0))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("MemoryLayer.import_from: skipping malformed entry: %s", exc)
                continue

            if merge:
                # Keep existing entry if it has a higher success_count.
                conn.execute(
                    """
                    INSERT INTO bubblegum_memory
                        (screen_sig, step_hash, ref, confidence, resolver_name,
                         metadata_json, last_success, success_count, failure_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(screen_sig, step_hash) DO UPDATE SET
                        ref           = CASE WHEN excluded.success_count > bubblegum_memory.success_count
                                             THEN excluded.ref           ELSE bubblegum_memory.ref END,
                        confidence    = CASE WHEN excluded.success_count > bubblegum_memory.success_count
                                             THEN excluded.confidence    ELSE bubblegum_memory.confidence END,
                        resolver_name = CASE WHEN excluded.success_count > bubblegum_memory.success_count
                                             THEN excluded.resolver_name ELSE bubblegum_memory.resolver_name END,
                        metadata_json = CASE WHEN excluded.success_count > bubblegum_memory.success_count
                                             THEN excluded.metadata_json ELSE bubblegum_memory.metadata_json END,
                        last_success  = CASE WHEN excluded.success_count > bubblegum_memory.success_count
                                             THEN excluded.last_success  ELSE bubblegum_memory.last_success END,
                        success_count = MAX(excluded.success_count, bubblegum_memory.success_count),
                        failure_count = MIN(excluded.failure_count, bubblegum_memory.failure_count)
                    """,
                    (screen_sig, step_hash, ref, confidence, resolver_name,
                     metadata_json, last_success, success_count, failure_count),
                )
            else:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO bubblegum_memory
                        (screen_sig, step_hash, ref, confidence, resolver_name,
                         metadata_json, last_success, success_count, failure_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (screen_sig, step_hash, ref, confidence, resolver_name,
                     metadata_json, last_success, success_count, failure_count),
                )
            imported += 1

        conn.commit()
        logger.info("MemoryLayer: imported %d entries from %s", imported, path)
        return imported

    def stats(self) -> dict:
        """Return summary statistics about the current cache contents."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*), SUM(success_count), SUM(failure_count) FROM bubblegum_memory"
        ).fetchone()
        total, successes, failures = row if row else (0, 0, 0)
        return {
            "total_entries": total or 0,
            "total_successes": successes or 0,
            "total_failures": failures or 0,
            "db_path": str(self._db_path),
        }

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
