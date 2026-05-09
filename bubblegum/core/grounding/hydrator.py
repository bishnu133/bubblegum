from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from bubblegum.core.schemas import ResolvedTarget, StepIntent

HydrationStatus = Literal["hydrated", "not_hydrated", "blocked"]

_UNSAFE_METADATA_KEYS = {
    "screenshot",
    "screenshot_bytes",
    "image_bytes",
    "base64",
    "raw_payload",
}


def is_visual_ref(ref: str) -> bool:
    """Return True when ref uses a synthetic visual scheme."""
    return isinstance(ref, str) and (ref.startswith("ocr://") or ref.startswith("vision://"))


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in _UNSAFE_METADATA_KEYS:
            continue
        out[key] = value
    return out


def _pick_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _text_ref(value: str) -> str:
    return f'text="{value}"'


def _role_ref(role: str, name: str) -> str:
    safe_role = role.strip()
    safe_name = name.strip()
    return f'role={safe_role}[name="{safe_name}"]'


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
    Phase 13I deterministic web-only mapping MVP:
    - Detect synthetic visual refs (ocr://, vision://).
    - Never execute synthetic refs directly.
    - Do not request screenshots, call providers, or perform center-click fallback.
    - Hydrate only when deterministic metadata can map to existing executable web refs.
    """

    def hydrate(self, *, target: ResolvedTarget, intent: StepIntent) -> HydrationResult:
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

        if intent.channel != "web":
            return HydrationResult(
                status="not_hydrated",
                target=None,
                reason="mobile_visual_hydration_not_supported",
                diagnostics={"channel": intent.channel},
                original_ref=ref,
                hydrated_ref=None,
            )

        metadata = _safe_metadata(dict(target.metadata))

        if ref.startswith("ocr://"):
            text = _pick_text(metadata, "matched_text", "text")
            if not text:
                return self._failsafe(ref=ref, scheme="ocr")
            hydrated_target = self._hydrated_target(
                target=target,
                hydrated_ref=_text_ref(text),
                source="ocr",
                strategy="text",
                metadata=metadata,
            )
            return HydrationResult(
                status="hydrated",
                target=hydrated_target,
                reason="hydrated_text_ref",
                diagnostics={"scheme": "ocr", "strategy": "text"},
                original_ref=ref,
                hydrated_ref=hydrated_target.ref,
            )

        if ref.startswith("vision://"):
            role = _pick_text(metadata, "role")
            name = _pick_text(metadata, "matched_text", "label", "text")
            if role and name:
                strategy = "role_text"
                hydrated_ref = _role_ref(role, name)
            elif name:
                strategy = "text"
                hydrated_ref = _text_ref(name)
            else:
                return self._failsafe(ref=ref, scheme="vision")

            hydrated_target = self._hydrated_target(
                target=target,
                hydrated_ref=hydrated_ref,
                source="vision",
                strategy=strategy,
                metadata=metadata,
            )
            return HydrationResult(
                status="hydrated",
                target=hydrated_target,
                reason="hydrated_visual_ref",
                diagnostics={"scheme": "vision", "strategy": strategy},
                original_ref=ref,
                hydrated_ref=hydrated_target.ref,
            )

        return self._failsafe(ref=ref, scheme="unknown")

    def _failsafe(self, *, ref: str, scheme: str) -> HydrationResult:
        return HydrationResult(
            status="not_hydrated",
            target=None,
            reason="unsupported_visual_ref_hydration",
            diagnostics={"scheme": scheme},
            original_ref=ref,
            hydrated_ref=None,
        )

    def _hydrated_target(
        self,
        *,
        target: ResolvedTarget,
        hydrated_ref: str,
        source: str,
        strategy: str,
        metadata: dict[str, Any],
    ) -> ResolvedTarget:
        hydration_confidence = float(target.confidence)
        enriched_metadata = dict(metadata)
        enriched_metadata.update(
            {
                "hydrated_from_ref": target.ref,
                "hydration_source": source,
                "hydration_strategy": strategy,
                "hydration_confidence": hydration_confidence,
            }
        )
        return target.model_copy(update={"ref": hydrated_ref, "metadata": enriched_metadata})
