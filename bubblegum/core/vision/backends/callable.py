from __future__ import annotations

from typing import Any, Callable

from bubblegum.core.vision.engine import VisionCandidate


class CallableVisionProvider:
    """VisionProvider adapter backed by a user-supplied callable."""

    def __init__(
        self,
        fn: Callable[[bytes, str, dict[str, Any] | None], list[VisionCandidate] | list[dict[str, Any]]],
    ) -> None:
        self._fn = fn

    def detect_targets(
        self,
        image_bytes: bytes,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> list[VisionCandidate] | list[dict[str, Any]]:
        return self._fn(image_bytes, instruction, context)
