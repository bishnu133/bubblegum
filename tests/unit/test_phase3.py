"""
tests/unit/test_phase3.py
==========================
Phase 3 unit tests — Memory self-healing.

Coverage:
  Group A — compute_signature (fingerprint.py)
    A1  Stability: same URL + same snapshot → same hash
    A2  Stability: whitespace variations in snapshot → same hash
    A3  Stability: line-order variation in snapshot → same hash
    A4  Stability: URL trailing slash normalised → same hash
    A5  Sensitivity: different URL → different hash
    A6  Sensitivity: different snapshot content → different hash
    A7  None snapshot: produces a valid hash (URL-only)
    A8  Empty string snapshot: same as None
    A9  Hash length: always 32 hex chars
    A10 Hash character set: only [0-9a-f]

  Group B — MemoryLayer (layer.py)
    B1  record_success + lookup → CacheEntry returned
    B2  lookup miss → None
    B3  lookup TTL expired → None
    B4  lookup failure_count >= max_failures → None
    B5  record_failure increments failure_count
    B6  record_failure to max_failures → lookup returns None
    B7  record_success resets failure_count to 0 on upsert
    B8  record_success increments success_count on repeat upsert
    B9  metadata round-trips through JSON
    B10 close() is idempotent (safe to call twice)
    B11 lookup with wrong step_hash → None
    B12 lookup with wrong screen_sig → None

  Group C — MemoryCacheResolver (memory_cache.py)
    C1  resolve() miss returns []
    C2  resolve() skipped when screen_signature absent from context
    C3  record_success → resolve() returns cached ResolvedTarget
    C4  cached_from metadata field reflects original resolver_name
    C5  resolver_name on hit is "memory_cache" (not original resolver)
    C6  confidence on hit matches recorded confidence
    C7  record_failure invalidates cache after max_failures
    C8  TTL expiry: stale entry returns []
    C9  Different step instructions produce different cache entries
    C10 Same instruction, different channel → different step_hash → separate entries
    C11 required_context() returns ["screen_signature"]
    C12 tier == 1, priority == 10, cost_level == "low"

  Group D — Self-healing end-to-end (no adapter required)
    D1  First resolve → miss; record_success; second resolve → hit (no other resolver)
    D2  After cache hit, resolver_name is "memory_cache" in ResolvedTarget
    D3  record_failure × max_failures then resolve → [] (cache invalidated)
    D4  record_success after failures resets and gives hit
"""

from __future__ import annotations

import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bubblegum.core.memory.fingerprint import compute_signature
from bubblegum.core.memory.layer import CacheEntry, MemoryLayer
from bubblegum.core.grounding.resolvers.memory_cache import (
    MemoryCacheResolver,
    _step_hash,
)
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_layer() -> tuple[MemoryLayer, Path]:
    """Return a MemoryLayer backed by a fresh temp DB, plus the temp dir path."""
    tmp = tempfile.mkdtemp()
    db  = Path(tmp) / "test.db"
    return MemoryLayer(db_path=db), Path(tmp)


def _tmp_resolver() -> MemoryCacheResolver:
    tmp = tempfile.mkdtemp()
    return MemoryCacheResolver(db_path=Path(tmp) / "test.db")


def _intent(
    instruction: str = "Click Login",
    channel: str = "web",
    action_type: str = "click",
    screen_sig: str = "sig_abc123",
) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel=channel,
        action_type=action_type,
        options=ExecutionOptions(),
        context={"screen_signature": screen_sig} if screen_sig else {},
    )


def _target(
    ref: str = 'role=button[name="Login"]',
    confidence: float = 0.94,
    resolver_name: str = "accessibility_tree",
    metadata: dict | None = None,
) -> ResolvedTarget:
    return ResolvedTarget(
        ref=ref,
        confidence=confidence,
        resolver_name=resolver_name,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Group A — compute_signature
# ---------------------------------------------------------------------------

class TestComputeSignature:

    def test_a1_stability_same_inputs(self):
        """Same URL + same snapshot always produces the same hash."""
        url      = "https://example.com/login"
        snapshot = "- button Login\n- input[type=text] username"
        h1 = compute_signature(url, snapshot)
        h2 = compute_signature(url, snapshot)
        assert h1 == h2

    def test_a2_stability_whitespace_variation(self):
        """Leading/trailing whitespace on snapshot lines is normalised away."""
        url = "https://example.com"
        h1  = compute_signature(url, "  button Login  \n  input Username")
        h2  = compute_signature(url, "button Login\ninput Username")
        assert h1 == h2

    def test_a3_stability_line_order(self):
        """Line order in snapshot does not affect the hash (lines are sorted)."""
        url = "https://example.com"
        h1  = compute_signature(url, "button Login\ninput Email")
        h2  = compute_signature(url, "input Email\nbutton Login")
        assert h1 == h2

    def test_a4_stability_trailing_slash_url(self):
        """Trailing slash on URL is stripped before hashing."""
        snap = "button Submit"
        h1   = compute_signature("https://example.com/page/", snap)
        h2   = compute_signature("https://example.com/page",  snap)
        assert h1 == h2

    def test_a5_sensitivity_different_url(self):
        """Different URL produces a different hash even with same snapshot."""
        snap = "button Login"
        h1   = compute_signature("https://example.com/login",   snap)
        h2   = compute_signature("https://example.com/register", snap)
        assert h1 != h2

    def test_a6_sensitivity_different_snapshot(self):
        """Different snapshot content produces a different hash."""
        url = "https://example.com"
        h1  = compute_signature(url, "button Login")
        h2  = compute_signature(url, "button Sign In")
        assert h1 != h2

    def test_a7_none_snapshot(self):
        """None snapshot is accepted; produces a URL-only hash (not empty string)."""
        sig = compute_signature("https://example.com", None)
        assert isinstance(sig, str)
        assert len(sig) == 32

    def test_a8_empty_snapshot_equals_none(self):
        """Empty string snapshot equals None for hashing purposes."""
        url = "https://example.com"
        h1  = compute_signature(url, None)
        h2  = compute_signature(url, "")
        assert h1 == h2

    def test_a9_hash_length(self):
        """Hash is always exactly 32 hex characters."""
        sig = compute_signature("https://example.com", "button Login")
        assert len(sig) == 32

    def test_a10_hash_charset(self):
        """Hash contains only lowercase hex characters."""
        sig = compute_signature("https://example.com", "button Login\ninput Email")
        assert re.fullmatch(r"[0-9a-f]{32}", sig)


# ---------------------------------------------------------------------------
# Group B — MemoryLayer
# ---------------------------------------------------------------------------

class TestMemoryLayer:

    def test_b1_record_and_lookup_hit(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig1", "hash1", "accessibility_tree",
                             'role=button[name="Login"]', 0.94)
        entry = layer.lookup("sig1", "hash1", ttl_days=7, max_failures=3)
        assert entry is not None
        assert entry.ref == 'role=button[name="Login"]'
        assert entry.confidence == pytest.approx(0.94)
        assert entry.resolver_name == "accessibility_tree"
        layer.close()

    def test_b2_lookup_miss(self):
        layer, _ = _tmp_layer()
        entry = layer.lookup("nosig", "nohash", ttl_days=7, max_failures=3)
        assert entry is None
        layer.close()

    def test_b3_ttl_expired(self):
        """Manually insert an expired row and confirm lookup returns None."""
        layer, _ = _tmp_layer()
        # Insert directly with an old timestamp
        conn = layer._get_conn()
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
        conn.execute(
            """
            INSERT INTO bubblegum_memory
                (screen_sig, step_hash, ref, confidence, resolver_name,
                 metadata_json, last_success, success_count, failure_count)
            VALUES (?, ?, ?, ?, ?, '{}', ?, 1, 0)
            """,
            ("stale_sig", "stale_hash", "button", 0.90, "exact_text", old_ts),
        )
        conn.commit()
        entry = layer.lookup("stale_sig", "stale_hash", ttl_days=7, max_failures=3)
        assert entry is None
        layer.close()

    def test_b4_failure_count_exceeded(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig2", "hash2", "exact_text", "text=Submit", 0.88)
        # Simulate max_failures failures
        for _ in range(3):
            layer.record_failure("sig2", "hash2")
        entry = layer.lookup("sig2", "hash2", ttl_days=7, max_failures=3)
        assert entry is None
        layer.close()

    def test_b5_record_failure_increments_count(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig3", "hash3", "exact_text", "text=Go", 0.80)
        layer.record_failure("sig3", "hash3")
        layer.record_failure("sig3", "hash3")
        # 2 failures, max is 3 → still a hit
        entry = layer.lookup("sig3", "hash3", ttl_days=7, max_failures=3)
        assert entry is not None
        layer.close()

    def test_b6_record_failure_to_max_then_miss(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig4", "hash4", "fuzzy_text", "text~=Login", 0.72)
        for _ in range(3):
            layer.record_failure("sig4", "hash4")
        assert layer.lookup("sig4", "hash4", ttl_days=7, max_failures=3) is None
        layer.close()

    def test_b7_record_success_resets_failure_count(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig5", "hash5", "exact_text", "text=OK", 0.85)
        layer.record_failure("sig5", "hash5")
        layer.record_failure("sig5", "hash5")
        # Re-record success → failure_count resets to 0
        layer.record_success("sig5", "hash5", "accessibility_tree",
                             'role=button[name="OK"]', 0.95)
        entry = layer.lookup("sig5", "hash5", ttl_days=7, max_failures=3)
        assert entry is not None
        assert entry.confidence == pytest.approx(0.95)
        layer.close()

    def test_b8_record_success_increments_success_count(self):
        layer, _ = _tmp_layer()
        layer.record_success("sig6", "hash6", "exact_text", "text=Go", 0.80)
        layer.record_success("sig6", "hash6", "exact_text", "text=Go", 0.82)
        # Directly query success_count
        conn = layer._get_conn()
        row  = conn.execute(
            "SELECT success_count FROM bubblegum_memory WHERE screen_sig=? AND step_hash=?",
            ("sig6", "hash6"),
        ).fetchone()
        assert row[0] == 2
        layer.close()

    def test_b9_metadata_round_trips(self):
        layer, _ = _tmp_layer()
        meta = {"matched_text": "Login", "role": "button", "index": 0}
        layer.record_success("sig7", "hash7", "accessibility_tree",
                             'role=button[name="Login"]', 0.94, metadata=meta)
        entry = layer.lookup("sig7", "hash7", ttl_days=7, max_failures=3)
        assert entry is not None
        assert entry.metadata == meta
        layer.close()

    def test_b10_close_idempotent(self):
        layer, _ = _tmp_layer()
        layer.close()
        layer.close()  # should not raise

    def test_b11_wrong_step_hash_miss(self):
        layer, _ = _tmp_layer()
        layer.record_success("sigX", "hashX", "exact_text", "text=A", 0.80)
        assert layer.lookup("sigX", "WRONG", ttl_days=7, max_failures=3) is None
        layer.close()

    def test_b12_wrong_screen_sig_miss(self):
        layer, _ = _tmp_layer()
        layer.record_success("sigY", "hashY", "exact_text", "text=B", 0.80)
        assert layer.lookup("WRONG", "hashY", ttl_days=7, max_failures=3) is None
        layer.close()


# ---------------------------------------------------------------------------
# Group C — MemoryCacheResolver
# ---------------------------------------------------------------------------

class TestMemoryCacheResolver:

    def test_c1_resolve_miss_returns_empty(self):
        r = _tmp_resolver()
        assert r.resolve(_intent()) == []
        r.close()

    def test_c2_skipped_when_no_screen_signature(self):
        r = _tmp_resolver()
        intent = _intent(screen_sig="")
        # Remove the key entirely
        intent.context.pop("screen_signature", None)
        assert r.resolve(intent) == []
        r.close()

    def test_c3_hit_after_record_success(self):
        r      = _tmp_resolver()
        intent = _intent()
        tgt    = _target()
        r.record_success(intent, tgt)
        result = r.resolve(intent)
        assert len(result) == 1
        assert result[0].ref == tgt.ref
        r.close()

    def test_c4_cached_from_metadata(self):
        r      = _tmp_resolver()
        intent = _intent()
        tgt    = _target(resolver_name="accessibility_tree")
        r.record_success(intent, tgt)
        result = r.resolve(intent)
        assert result[0].metadata.get("cached_from") == "accessibility_tree"
        r.close()

    def test_c5_resolver_name_is_memory_cache(self):
        r      = _tmp_resolver()
        intent = _intent()
        r.record_success(intent, _target())
        result = r.resolve(intent)
        assert result[0].resolver_name == "memory_cache"
        r.close()

    def test_c6_confidence_matches_recorded(self):
        r      = _tmp_resolver()
        intent = _intent()
        tgt    = _target(confidence=0.91)
        r.record_success(intent, tgt)
        result = r.resolve(intent)
        assert result[0].confidence == pytest.approx(0.91)
        r.close()

    def test_c7_record_failure_invalidates_cache(self):
        r      = _tmp_resolver()
        intent = _intent()
        r.record_success(intent, _target())
        # 3 failures → invalidated
        for _ in range(3):
            r.record_failure(intent)
        assert r.resolve(intent) == []
        r.close()

    def test_c8_ttl_expiry_returns_empty(self):
        """Inject an expired row directly into the DB and confirm miss."""
        r   = _tmp_resolver()
        old = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat()
        conn = r._layer._get_conn()
        conn.execute(
            """
            INSERT INTO bubblegum_memory
                (screen_sig, step_hash, ref, confidence, resolver_name,
                 metadata_json, last_success, success_count, failure_count)
            VALUES (?, ?, ?, ?, ?, '{}', ?, 1, 0)
            """,
            ("sig_abc123", _step_hash(_intent()), "text=Login", 0.90, "exact_text", old),
        )
        conn.commit()
        assert r.resolve(_intent()) == []
        r.close()

    def test_c9_different_instructions_separate_entries(self):
        r       = _tmp_resolver()
        intent1 = _intent(instruction="Click Login")
        intent2 = _intent(instruction="Click Register")
        r.record_success(intent1, _target(ref="text=Login"))
        r.record_success(intent2, _target(ref="text=Register"))
        assert r.resolve(intent1)[0].ref == "text=Login"
        assert r.resolve(intent2)[0].ref == "text=Register"
        r.close()

    def test_c10_different_channel_separate_entries(self):
        r        = _tmp_resolver()
        intent_w = _intent(channel="web",    screen_sig="sig_shared")
        intent_m = _intent(channel="mobile", screen_sig="sig_shared")
        r.record_success(intent_w, _target(ref="role=button", confidence=0.90))
        r.record_success(intent_m, _target(ref="id=login_btn", confidence=0.85))
        web_hit    = r.resolve(intent_w)
        mobile_hit = r.resolve(intent_m)
        assert web_hit[0].ref    == "role=button"
        assert mobile_hit[0].ref == "id=login_btn"
        r.close()

    def test_c11_required_context(self):
        r = _tmp_resolver()
        assert r.required_context() == ["screen_signature"]
        r.close()

    def test_c12_resolver_attributes(self):
        r = _tmp_resolver()
        assert r.tier       == 1
        assert r.priority   == 10
        assert r.cost_level == "low"
        assert "web"    in r.channels
        assert "mobile" in r.channels
        r.close()


# ---------------------------------------------------------------------------
# Group D — Self-healing end-to-end (no adapter)
# ---------------------------------------------------------------------------

class TestSelfHealingEndToEnd:

    def test_d1_miss_then_record_then_hit(self):
        """First resolve misses; after record_success second resolve hits."""
        r      = _tmp_resolver()
        intent = _intent()

        # Run 1: miss
        assert r.resolve(intent) == []

        # Simulate SDK recording the winning target
        tgt = _target()
        r.record_success(intent, tgt)

        # Run 2: cache hit
        hits = r.resolve(intent)
        assert len(hits) == 1
        assert hits[0].ref == tgt.ref
        r.close()

    def test_d2_hit_resolver_name_is_memory_cache(self):
        r      = _tmp_resolver()
        intent = _intent()
        r.record_success(intent, _target(resolver_name="fuzzy_text"))
        hits = r.resolve(intent)
        assert hits[0].resolver_name == "memory_cache"
        r.close()

    def test_d3_failure_loop_invalidates_then_miss(self):
        r      = _tmp_resolver()
        intent = _intent()
        r.record_success(intent, _target())

        for _ in range(3):
            r.record_failure(intent)

        assert r.resolve(intent) == []
        r.close()

    def test_d4_record_success_after_failures_restores_cache(self):
        r      = _tmp_resolver()
        intent = _intent()
        r.record_success(intent, _target(ref="text=Login", confidence=0.88))

        # Push to failure limit
        for _ in range(3):
            r.record_failure(intent)
        assert r.resolve(intent) == []

        # New successful resolution (e.g. LLM found it again)
        r.record_success(intent, _target(ref='role=button[name="Login"]', confidence=0.95))
        hits = r.resolve(intent)
        assert len(hits) == 1
        assert hits[0].ref == 'role=button[name="Login"]'
        assert hits[0].confidence == pytest.approx(0.95)
        r.close()
