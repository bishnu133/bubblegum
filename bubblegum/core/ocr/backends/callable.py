from __future__ import annotations

from typing import Any, Callable

from bubblegum.core.ocr.engine import OCRBlock


class CallableOCREngine:
    """OCREngine adapter backed by a user-supplied callable."""

    def __init__(
        self,
        fn: Callable[[bytes], list[OCRBlock] | list[dict[str, Any]]],
    ) -> None:
        self._fn = fn

    def extract_blocks(self, image_bytes: bytes) -> list[OCRBlock] | list[dict[str, Any]]:
        return self._fn(image_bytes)
