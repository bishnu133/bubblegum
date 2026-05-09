"""Deterministic OCR callable + hydration pattern example.

This file is compile-safe/import-safe and intentionally avoids any external OCR provider,
network call, screenshot provider call, or adapter execution.
"""

from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget


def fake_ocr_callable(_image_bytes: bytes, _instruction: str, _context: dict | None = None) -> list[dict]:
    """Deterministic fake OCR response."""
    return [
        {
            "text": "Continue",
            "confidence": 0.98,
            "bbox": {"x": 120, "y": 80, "w": 160, "h": 40},
        }
    ]


def build_synthetic_ocr_target() -> ResolvedTarget:
    """Return a synthetic OCR target showing hydration metadata shape."""
    blocks = fake_ocr_callable(b"fake-image-bytes", "Tap Continue")
    top = blocks[0]
    return ResolvedTarget(
        ref="ocr://block/0",
        confidence=float(top["confidence"]),
        resolver_name="OCRResolver",
        metadata={
            "source": "ocr",
            "matched_text": top["text"],
            "ocr_confidence": top["confidence"],
        },
    )


def describe_hydration_pattern() -> str:
    """Human-readable pattern for deterministic hydration behavior."""
    target = build_synthetic_ocr_target()
    return (
        "Synthetic OCR candidate created: "
        f"ref={target.ref}, matched_text={target.metadata.get('matched_text')!r}. "
        "In runtime, VisualRefHydrator maps supported synthetic refs to executable refs "
        "using deterministic metadata and emits sanitized hydration diagnostics in reports."
    )


if __name__ == "__main__":
    print(describe_hydration_pattern())
