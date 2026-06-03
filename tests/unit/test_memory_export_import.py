"""Unit tests for MemoryLayer export / import / stats."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bubblegum.core.memory.layer import MemoryLayer


@pytest.fixture()
def layer(tmp_path):
    return MemoryLayer(db_path=tmp_path / "test.db")


def _seed(layer: MemoryLayer, n: int = 3) -> None:
    for i in range(n):
        layer.record_success(
            screen_signature=f"sig-{i}",
            step_hash=f"hash-{i}",
            resolver_name="accessibility_tree",
            ref=f'role=button[name="Btn{i}"]',
            confidence=0.95,
            metadata={"label": f"Btn{i}"},
        )


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_creates_json_file(layer, tmp_path):
    _seed(layer, 2)
    out = tmp_path / "cache.json"
    count = layer.export(out)

    assert count == 2
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["version"] == 1
    assert len(payload["entries"]) == 2


def test_export_entry_has_expected_fields(layer, tmp_path):
    _seed(layer, 1)
    out = tmp_path / "cache.json"
    layer.export(out)

    payload = json.loads(out.read_text())
    entry = payload["entries"][0]
    for field in ("screen_signature", "step_hash", "ref", "confidence",
                  "resolver_name", "last_success", "success_count", "failure_count"):
        assert field in entry, f"Missing field: {field}"


def test_export_empty_db(layer, tmp_path):
    out = tmp_path / "cache.json"
    count = layer.export(out)
    assert count == 0
    payload = json.loads(out.read_text())
    assert payload["entries"] == []


# ---------------------------------------------------------------------------
# import_from
# ---------------------------------------------------------------------------

def test_import_loads_entries(layer, tmp_path):
    _seed(layer, 3)
    out = tmp_path / "cache.json"
    layer.export(out)

    # Fresh layer
    layer2 = MemoryLayer(db_path=tmp_path / "test2.db")
    imported = layer2.import_from(out)

    assert imported == 3
    entry = layer2.lookup("sig-0", "hash-0", ttl_days=365, max_failures=100)
    assert entry is not None
    assert entry.ref == 'role=button[name="Btn0"]'


def test_import_idempotent(layer, tmp_path):
    _seed(layer, 2)
    out = tmp_path / "cache.json"
    layer.export(out)

    layer2 = MemoryLayer(db_path=tmp_path / "test2.db")
    layer2.import_from(out)
    layer2.import_from(out)   # second import — should not duplicate

    assert layer2.stats()["total_entries"] == 2


def test_import_merge_keeps_higher_success_count(layer, tmp_path):
    # Existing entry with success_count=5
    for _ in range(5):
        layer.record_success("sig-x", "hash-x", "accessibility_tree", "role=button", 0.9)

    out = tmp_path / "cache.json"
    layer.export(out)

    # Incoming entry has success_count=1
    layer2 = MemoryLayer(db_path=tmp_path / "test2.db")
    layer2.record_success("sig-x", "hash-x", "accessibility_tree", "role=button", 0.9)

    layer2.import_from(out, merge=True)

    stats = layer2.stats()
    # success_count should be MAX(5, 1) = 5
    assert stats["total_successes"] >= 5


def test_import_returns_zero_for_missing_file(layer, tmp_path):
    result = layer.import_from(tmp_path / "nonexistent.json")
    assert result == 0


def test_import_returns_zero_for_wrong_version(layer, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": 99, "entries": []}))
    result = layer.import_from(bad)
    assert result == 0


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def test_stats_empty(layer):
    s = layer.stats()
    assert s["total_entries"] == 0
    assert s["total_successes"] == 0


def test_stats_after_seeding(layer):
    _seed(layer, 3)
    s = layer.stats()
    assert s["total_entries"] == 3
    assert s["total_successes"] == 3
    assert "db_path" in s
