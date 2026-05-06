from __future__ import annotations

from bubblegum.core.ocr.backends import CallableOCREngine
from bubblegum.core.ocr.engine import OCRBlock, build_ocr_blocks_from_screenshot


def test_callable_backend_returns_blocks_and_pipeline_normalizes():
    def fn(_image_bytes: bytes):
        return [
            OCRBlock(text=" Continue ", bbox=(1, 2, 3, 4), confidence=0.9),
            {"text": "Sign In", "bbox": [10, 20, 30, 40], "confidence": 0.88},
        ]

    engine = CallableOCREngine(fn)
    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=engine,
    )

    assert out == [
        {"text": "Continue", "bbox": [1, 2, 3, 4], "confidence": 0.9},
        {"text": "Sign In", "bbox": [10, 20, 30, 40], "confidence": 0.88},
    ]


def test_callable_backend_malformed_output_is_dropped():
    engine = CallableOCREngine(lambda _image_bytes: [{"text": "", "bbox": [1, 2, 3, 4], "confidence": 0.5}, "bad"])
    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=engine,
    )
    assert out == []


def test_callable_exception_returns_empty_via_pipeline():
    def boom(_image_bytes: bytes):
        raise RuntimeError("boom")

    engine = CallableOCREngine(boom)
    out = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=engine,
    )
    assert out == []


def test_callable_not_invoked_when_disabled_or_gated_or_screenshot_missing():
    calls = {"count": 0}

    def fn(_image_bytes: bytes):
        calls["count"] += 1
        return []

    engine = CallableOCREngine(fn)

    out_disabled = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=False,
        process_screenshots_for_ocr=True,
        engine=engine,
    )
    out_gate_false = build_ocr_blocks_from_screenshot(
        screenshot=b"png",
        enabled=True,
        process_screenshots_for_ocr=False,
        engine=engine,
    )
    out_missing_screenshot = build_ocr_blocks_from_screenshot(
        screenshot=None,
        enabled=True,
        process_screenshots_for_ocr=True,
        engine=engine,
    )

    assert out_disabled == []
    assert out_gate_false == []
    assert out_missing_screenshot == []
    assert calls["count"] == 0
