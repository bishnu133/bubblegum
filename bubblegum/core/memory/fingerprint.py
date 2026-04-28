"""
bubblegum/core/memory/fingerprint.py
=====================================
Screen fingerprinting for the MemoryLayer.

compute_signature(url, a11y_snapshot) -> str
  Returns a stable, deterministic SHA-256 hex digest (first 32 chars) that
  identifies a unique page state.

Normalisation (applied before hashing so the same logical state always
produces the same hash regardless of whitespace variation):
  1. URL is stripped of trailing slashes and lowercased.
  2. a11y_snapshot lines are stripped of leading/trailing whitespace.
  3. Empty lines are discarded.
  4. Lines are sorted alphabetically (removes order sensitivity from
     accessibility tree serialisation differences across Playwright versions).
  5. Everything is lowercased.
  6. The normalised URL and snapshot are joined with a pipe separator before
     hashing.

Design properties:
  - Deterministic: identical inputs always produce the same hash.
  - Sensitive: different URL OR meaningfully different snapshot → different hash.
  - Stable across minor whitespace drift in the a11y tree (strip + sort).
  - Not sensitive to a11y tree *ordering* changes caused by Playwright internals
    (sort makes it order-independent).
  - Does NOT depend on screenshot bytes (expensive, non-deterministic across runs).

Phase 3.
"""

from __future__ import annotations

import hashlib


def compute_signature(url: str, a11y_snapshot: str | None) -> str:
    """
    Compute a stable screen signature for the given URL + a11y snapshot.

    Args:
        url:           The page URL (e.g. "https://example.com/login").
        a11y_snapshot: The raw aria_snapshot() string from Playwright.
                       May be None or empty (produces a URL-only hash).

    Returns:
        32-character hex string (first 128 bits of SHA-256).
    """
    # --- normalise URL ---
    norm_url = url.strip().rstrip("/").lower()

    # --- normalise snapshot ---
    snapshot_text = a11y_snapshot or ""
    lines: list[str] = []
    for line in snapshot_text.splitlines():
        stripped = line.strip().lower()
        if stripped:
            lines.append(stripped)
    lines.sort()
    norm_snapshot = "\n".join(lines)

    # --- hash ---
    payload = f"{norm_url}|{norm_snapshot}"
    digest  = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:32]
