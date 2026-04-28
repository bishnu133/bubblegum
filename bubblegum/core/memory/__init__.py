"""
bubblegum/core/memory
=====================
Memory self-healing layer — Phase 3.

Public exports:
  MemoryLayer      — SQLite-backed cache for (screen_sig, step_hash) → CacheEntry
  CacheEntry       — dataclass returned by MemoryLayer.lookup()
  compute_signature — deterministic SHA-256 screen fingerprint
"""

from bubblegum.core.memory.fingerprint import compute_signature
from bubblegum.core.memory.layer import CacheEntry, MemoryLayer

__all__ = ["MemoryLayer", "CacheEntry", "compute_signature"]