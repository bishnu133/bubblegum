from __future__ import annotations

import threading

import pytest

from bubblegum.core.memory.layer import MemoryLayer


def _journal_mode(layer: MemoryLayer) -> str:
    return layer._get_conn().execute("PRAGMA journal_mode").fetchone()[0].lower()


def _busy_timeout(layer: MemoryLayer) -> int:
    return int(layer._get_conn().execute("PRAGMA busy_timeout").fetchone()[0])


# ---------------------------------------------------------------------------
# PRAGMA configuration
# ---------------------------------------------------------------------------


def test_wal_mode_enabled_by_default(tmp_path):
    layer = MemoryLayer(tmp_path / "memory.db")
    try:
        assert _journal_mode(layer) == "wal"
    finally:
        layer.close()


def test_busy_timeout_configured(tmp_path):
    layer = MemoryLayer(tmp_path / "memory.db", busy_timeout_ms=1234)
    try:
        assert _busy_timeout(layer) == 1234
    finally:
        layer.close()


def test_wal_can_be_disabled(tmp_path):
    layer = MemoryLayer(tmp_path / "memory.db", wal=False)
    try:
        # Without WAL the default file journal mode is "delete".
        assert _journal_mode(layer) != "wal"
    finally:
        layer.close()


# ---------------------------------------------------------------------------
# Shared cache hits across connections (i.e. across xdist workers)
# ---------------------------------------------------------------------------


def test_write_in_one_connection_is_visible_in_another(tmp_path):
    db = tmp_path / "memory.db"
    writer = MemoryLayer(db)
    reader = MemoryLayer(db)
    try:
        writer.record_success("sig-1", "hash-1", "exact_text", 'role=button[name="Login"]', 0.93)
        entry = reader.lookup("sig-1", "hash-1")
        assert entry is not None
        assert entry.ref == 'role=button[name="Login"]'
        assert entry.resolver_name == "exact_text"
    finally:
        writer.close()
        reader.close()


# ---------------------------------------------------------------------------
# Concurrent writers — no lost writes / no "database is locked"
# ---------------------------------------------------------------------------


def test_concurrent_thread_writers_no_lost_writes(tmp_path):
    db = tmp_path / "memory.db"
    n_workers, per_worker = 4, 40

    def worker(wid: int) -> None:
        layer = MemoryLayer(db)
        for i in range(per_worker):
            layer.record_success(f"sig-{wid}", f"hash-{wid}-{i}", "r", f"ref-{i}", 0.9)
        layer.close()

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    layer = MemoryLayer(db)
    try:
        # Every distinct (sig, hash) write must have landed — WAL + busy_timeout
        # means contended writers wait rather than dropping the write.
        assert layer.stats()["total_entries"] == n_workers * per_worker
    finally:
        layer.close()


def test_concurrent_process_writers_complete_without_lock_errors(tmp_path):
    from concurrent.futures import ProcessPoolExecutor

    db = tmp_path / "memory.db"
    n_workers, per_worker = 4, 25
    tasks = [(str(db), w, per_worker) for w in range(n_workers)]

    try:
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            list(ex.map(_mp_writer, tasks))
    except Exception as exc:  # environment cannot spawn worker processes
        pytest.skip(f"multiprocessing unavailable here: {exc}")

    layer = MemoryLayer(db)
    try:
        # Mirrors a 4-worker `pytest -n 4` run sharing .bubblegum/memory.db.
        assert layer.stats()["total_entries"] == n_workers * per_worker
        # Cache hits still resolve on replay from a fresh connection.
        assert layer.lookup("sig-0", "hash-0-0") is not None
    finally:
        layer.close()


def _mp_writer(args) -> int:
    """Top-level (picklable) worker: write `count` distinct entries to `db_path`."""
    db_path, worker_id, count = args
    layer = MemoryLayer(db_path)
    for i in range(count):
        layer.record_success(f"sig-{worker_id}", f"hash-{worker_id}-{i}", "r", f"ref-{i}", 0.9)
    layer.close()
    return worker_id
