from __future__ import annotations

from bubblegum.core.ocr.engine import (
    OCRBlock,
    FakeOCREngine,
    build_ocr_blocks_from_screenshot,
    normalize_ocr_blocks,
)


def test_normalize_valid_ocr_blocks():
    raw = [{"text": " Sign In ", "bbox": [10, 20, 110, 60], "confidence": 0.85}]
    out = normalize_ocr_blocks(raw)
    assert out == [{"text": "Sign In", "bbox": [10, 20, 110, 60], "confidence": 0.85}]


def test_normalize_drops_empty_text():
    raw = [{"text": "   ", "bbox": [0, 0, 1, 1], "confidence": 0.9}]
    assert normalize_ocr_blocks(raw) == []


def test_normalize_drops_invalid_bbox():
    raw = [{"text": "Continue", "bbox": [0, 1, 2], "confidence": 0.9}]
    assert normalize_ocr_blocks(raw) == []


def test_normalize_clamps_confidence_and_coerces_coords_to_ints():
    raw = [{"text": "Continue", "bbox": [1.9, "2", 3.2, 4.0], "confidence": 9.2}]
    out = normalize_ocr_blocks(raw)
    assert out == [{"text": "Continue", "bbox": [1, 2, 3, 4], "confidence": 1.0}]


def test_fake_engine_returns_deterministic_blocks():
    engine = FakeOCREngine()
    out1 = normalize_ocr_blocks(engine.extract_blocks(b"abc"))
    out2 = normalize_ocr_blocks(engine.extract_blocks(b"xyz"))
    assert out1 == out2
    assert len(out1) == 2


def test_pipeline_returns_empty_when_disabled():
    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=False,
        process_screenshots_for_ocr=True,
        engine=FakeOCREngine(),
    )
    assert out == []


def test_pipeline_returns_empty_without_screenshot_bytes():
    out = build_ocr_blocks_from_screenshot(
        screenshot=None,
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=FakeOCREngine(),
    )
    assert out == []


def test_pipeline_returns_empty_when_engine_raises():
    class BadEngine:
        def extract_blocks(self, image_bytes: bytes):
            del image_bytes
            raise RuntimeError("boom")

    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=BadEngine(),
    )
    assert out == []


def test_pipeline_returns_normalized_blocks_when_enabled():
    engine = FakeOCREngine(
        blocks=[
            OCRBlock(text=" Continue ", bbox=(10, 20, 30, 40), confidence=0.9),
            {"text": "", "bbox": [1, 2, 3, 4], "confidence": 0.1},
        ]
    )
    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=engine,
    )
    assert out == [{"text": "Continue", "bbox": [10, 20, 30, 40], "confidence": 0.9}]
