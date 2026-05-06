from bubblegum.core.ocr.backends import CallableOCREngine
from bubblegum.core.ocr.engine import (
    OCRBlock,
    OCREngine,
    FakeOCREngine,
    build_ocr_blocks_from_screenshot,
    normalize_ocr_blocks,
)

__all__ = [
    "CallableOCREngine",
    "OCRBlock",
    "OCREngine",
    "FakeOCREngine",
    "build_ocr_blocks_from_screenshot",
    "normalize_ocr_blocks",
]
