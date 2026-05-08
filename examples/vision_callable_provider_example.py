"""Phase 11P: public callable vision provider registration example.

This example demonstrates the public provider lifecycle API using a deterministic,
local callable backend (no external vision service dependency).

Notes:
- `vision://...` references are synthetic resolver metadata, not executable selectors.
- Do not log/store raw screenshot bytes in traces or metadata.
"""

from __future__ import annotations

from typing import Any

from bubblegum import act, clear_vision_provider, configure_runtime, configure_vision_provider
from bubblegum.core.vision.backends.callable import CallableVisionProvider
from bubblegum.core.vision.engine import VisionCandidate


def fake_detect_targets(
    image_bytes: bytes,
    instruction: str,
    context: dict[str, Any] | None,
) -> list[VisionCandidate | dict[str, Any]]:
    """Deterministic fake callable.

    Accepts `(image_bytes, instruction, context)` and returns stable candidates.
    Intentionally does not print or persist raw screenshot bytes.
    """

    _ = len(image_bytes)  # consume bytes without logging/persisting payload
    channel = (context or {}).get("channel", "unknown")

    return [
        VisionCandidate(
            label="Submit",
            bbox=(100, 200, 180, 240),
            confidence=0.95,
            role="button",
            text=f"submit ({channel})",
        ),
        {
            "label": "Cancel",
            "bbox": [190, 200, 260, 240],
            "confidence": 0.76,
            "role": "button",
            "text": instruction[:32],
        },
    ]


async def run_example(page: Any) -> None:
    """Illustrative flow showing provider setup + teardown with required gates."""

    provider = CallableVisionProvider(fake_detect_targets)
    configure_vision_provider(provider)

    try:
        configure_runtime(
            {
                "grounding": {"enable_vision": True},
                "privacy": {
                    "send_screenshots": True,
                    "process_screenshots_for_vision": True,
                },
            }
        )

        await act(
            page=page,
            instruction="Click the primary submit button",
        )

        # If vision contributes, resolver metadata may contain refs like
        # `vision://target/0`; these are synthetic/non-executable references.
    finally:
        # Always clear global registration between tests/sessions.
        clear_vision_provider()


if __name__ == "__main__":
    print(
        "This module is import/compile-safe and intended to be copied into "
        "your existing async Playwright/Appium test harness."
    )
