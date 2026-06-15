"""
bubblegum/core/visual.py
========================
Pure visual-regression logic (V1) — no image-codec dependency.

The pixel math here operates on raw RGBA byte buffers so it is fully
unit-testable without Pillow or a browser. PNG decode/encode (the only part
that needs Pillow) lives in ``bubblegum.core.visual_image``; the assertion
wiring is in ``sdk._verify_visual``.

Pieces:
  - ``baseline_name``       derive a stable baseline key from the instruction
  - ``compare_rgba``        count differing pixels between two equal-size buffers
  - ``evaluate_diff``       decide pass/fail against a tolerance
  - ``highlight_diff_rgba`` build a diff image highlighting changed pixels
"""

from __future__ import annotations

import re

_NAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Leading verbs / trailing "matches baseline"-style phrasing stripped so
# "Verify the header matches baseline" → "header".
_LEADING_VERB_RE = re.compile(
    r"^\s*(?:verify|check|assert|confirm|ensure|see|that)\s+", re.IGNORECASE
)
_TRAILING_BASELINE_RE = re.compile(
    r"\s*(?:matches?|match|against|vs\.?|equals?)?\s*(?:the\s+)?baseline\s*$",
    re.IGNORECASE,
)
_TRAILING_STATE_RE = re.compile(
    r"\s*(?:looks?|is|are)\s+(?:the\s+same|unchanged|correct|identical)\s*$",
    re.IGNORECASE,
)


def _strip_visual_phrases(text: str) -> str:
    t = (text or "").strip()
    t = _LEADING_VERB_RE.sub("", t)
    t = _TRAILING_BASELINE_RE.sub("", t)
    t = _TRAILING_STATE_RE.sub("", t)
    t = re.sub(r"^\s*(?:the|a|an)\s+", "", t, flags=re.IGNORECASE)
    return t.strip()


def baseline_name(
    instruction: str,
    expected_value: str | None = None,
    screen_signature: str | None = None,
) -> str:
    """Derive a filesystem-safe baseline key.

    Prefers an explicit ``expected_value``, else the instruction with its
    visual phrasing stripped ("header matches baseline" → "header"), else the
    screen signature, else "baseline".
    """
    raw = (expected_value or "").strip() or _strip_visual_phrases(instruction)
    cleaned = _NAME_SANITIZE_RE.sub("_", raw).strip("_").lower()
    if cleaned:
        return cleaned
    if screen_signature:
        return _NAME_SANITIZE_RE.sub("_", screen_signature).strip("_").lower()[:40] or "baseline"
    return "baseline"


def compare_rgba(
    baseline: bytes,
    actual: bytes,
    width: int,
    height: int,
    *,
    channel_threshold: int = 0,
) -> tuple[int, int, bytes]:
    """Compare two equal-size RGBA buffers pixel-by-pixel.

    Returns ``(diff_pixels, total_pixels, mask)`` where ``mask`` has one byte
    per pixel (1 = changed). A pixel counts as changed when the max per-channel
    absolute delta exceeds ``channel_threshold``.

    Raises ValueError if either buffer is not exactly ``width*height*4`` bytes.
    """
    total = width * height
    expected_len = total * 4
    if len(baseline) != expected_len or len(actual) != expected_len:
        raise ValueError(
            f"RGBA buffer size mismatch: expected {expected_len} bytes "
            f"(baseline={len(baseline)}, actual={len(actual)})"
        )

    mask = bytearray(total)
    diff = 0
    for i in range(total):
        o = i * 4
        d = max(
            abs(baseline[o] - actual[o]),
            abs(baseline[o + 1] - actual[o + 1]),
            abs(baseline[o + 2] - actual[o + 2]),
            abs(baseline[o + 3] - actual[o + 3]),
        )
        if d > channel_threshold:
            diff += 1
            mask[i] = 1
    return diff, total, bytes(mask)


def diff_ratio(diff_pixels: int, total_pixels: int) -> float:
    """Fraction of pixels that changed (0.0 when there are no pixels)."""
    if total_pixels <= 0:
        return 0.0
    return diff_pixels / total_pixels


def evaluate_diff(diff_pixels: int, total_pixels: int, tolerance: float) -> tuple[bool, float]:
    """Return ``(passed, ratio)`` — passed when ratio <= tolerance."""
    ratio = diff_ratio(diff_pixels, total_pixels)
    return ratio <= tolerance, ratio


def highlight_diff_rgba(
    actual: bytes,
    mask: bytes,
    width: int,
    height: int,
    *,
    highlight: tuple[int, int, int, int] = (255, 0, 0, 255),
) -> bytes:
    """Build a diff image: changed pixels painted ``highlight``, others dimmed.

    Dimming the unchanged region (blended toward white) makes the highlighted
    differences pop in the saved artifact.
    """
    total = width * height
    if len(actual) != total * 4 or len(mask) != total:
        raise ValueError("highlight_diff_rgba: buffer/mask size mismatch")

    out = bytearray(actual)
    hr, hg, hb, ha = highlight
    for i in range(total):
        o = i * 4
        if mask[i]:
            out[o], out[o + 1], out[o + 2], out[o + 3] = hr, hg, hb, ha
        else:
            # Blend toward white (≈ 65% lighter) but keep full alpha.
            out[o] = (actual[o] + 2 * 255) // 3
            out[o + 1] = (actual[o + 1] + 2 * 255) // 3
            out[o + 2] = (actual[o + 2] + 2 * 255) // 3
            out[o + 3] = 255
    return bytes(out)
