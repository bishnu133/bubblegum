from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OCRBlock:
    """Normalized OCR block representation."""

    text: str
    bbox: tuple[int, int, int, int]
    confidence: float


class OCREngine(Protocol):
    """Adapter-neutral OCR engine protocol."""

    def extract_blocks(self, image_bytes: bytes) -> list[OCRBlock] | list[dict[str, Any]]:
        """Extract OCR blocks from screenshot bytes."""


class FakeOCREngine:
    """Deterministic fake OCR engine for tests and local wiring."""

    def __init__(self, blocks: list[OCRBlock] | list[dict[str, Any]] | None = None) -> None:
        self._blocks = blocks or [
            OCRBlock(text="Continue", bbox=(112, 420, 264, 478), confidence=0.98),
            OCRBlock(text="Cart (2)", bbox=(310, 40, 392, 88), confidence=0.95),
        ]

    def extract_blocks(self, image_bytes: bytes) -> list[OCRBlock] | list[dict[str, Any]]:
        del image_bytes
        return list(self._blocks)


def normalize_ocr_blocks(raw_blocks: list[Any]) -> list[dict[str, Any]]:
    """Normalize raw OCR output to canonical context['ocr_blocks'] shape."""
    normalized: list[dict[str, Any]] = []

    for raw in raw_blocks:
        parsed = _normalize_single_block(raw)
        if parsed is None:
            continue
        normalized.append(parsed)

    return normalized


def build_ocr_blocks_from_screenshot(
    *,
    screenshot: bytes | None,
    enabled: bool,
    process_screenshots_for_ocr: bool,
    engine: OCREngine | None,
) -> list[dict[str, Any]]:
    """Safely build normalized OCR blocks from screenshot bytes."""
    if not enabled or not process_screenshots_for_ocr:
        return []
    if not screenshot or engine is None:
        return []

    try:
        raw_blocks = engine.extract_blocks(screenshot)
    except Exception:
        return []

    if not isinstance(raw_blocks, list):
        return []

    return normalize_ocr_blocks(raw_blocks)


def _normalize_single_block(raw: Any) -> dict[str, Any] | None:
    text: str | None = None
    bbox: Any = None
    confidence: Any = None

    if isinstance(raw, OCRBlock):
        text = raw.text
        bbox = list(raw.bbox)
        confidence = raw.confidence
    elif isinstance(raw, dict):
        text = raw.get("text")
        bbox = raw.get("bbox")
        confidence = raw.get("confidence")
    else:
        return None

    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None

    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        bbox_ints = [int(float(v)) for v in bbox]
    except (TypeError, ValueError):
        return None

    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return None

    conf = min(max(conf, 0.0), 1.0)

    return {
        "text": text,
        "bbox": bbox_ints,
        "confidence": conf,
    }
