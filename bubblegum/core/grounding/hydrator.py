from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from bubblegum.core.schemas import ResolvedTarget, StepIntent

HydrationStatus = Literal["hydrated", "not_hydrated", "blocked"]


def is_visual_ref(ref: str) -> bool:
    """Return True when ref uses a synthetic visual scheme."""
    return isinstance(ref, str) and (ref.startswith("ocr://") or ref.startswith("vision://"))


@dataclass(frozen=True)
class HydrationResult:
    status: HydrationStatus
    target: ResolvedTarget | None
    reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    original_ref: str | None = None
    hydrated_ref: str | None = None


class VisualRefHydrator:
    """
    Phase 13G fail-safe MVP:
    - Detect synthetic visual refs (ocr://, vision://).
    - Do not execute synthetic refs directly.
    - Do not request screenshots, call providers, or perform center-click fallback.
    """

    def hydrate(self, *, target: ResolvedTarget, intent: StepIntent) -> HydrationResult:
        del intent
        ref = target.ref

        if not is_visual_ref(ref):
            return HydrationResult(
                status="not_hydrated",
                target=target,
                reason="not_visual_ref",
                diagnostics={},
                original_ref=ref,
                hydrated_ref=ref,
            )

        return HydrationResult(
            status="not_hydrated",
            target=None,
            reason="unsupported_visual_ref_hydration",
            diagnostics={"scheme": "ocr" if ref.startswith("ocr://") else "vision"},
            original_ref=ref,
            hydrated_ref=None,
        )
