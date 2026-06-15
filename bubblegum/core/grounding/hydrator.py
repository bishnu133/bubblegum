from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Literal
import xml.etree.ElementTree as ET

from bubblegum.core.coordinates import (
    COORDINATE_CLICK_ACTIONS,
    bbox_center,
    coordinate_ref,
)
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


def _safe_diag(diagnostics: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in diagnostics.items():
        if key in _UNSAFE_METADATA_KEYS:
            continue
        if key in {"hierarchy_xml", "a11y_snapshot", "candidate_dump", "candidates"}:
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


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    parts = value.split("'")
    concat_args = ', "\'", '.join(f"'{p}'" for p in parts)
    return f"concat({concat_args})"


def _xpath_ref_for_attr(attr: str, value: str) -> str:
    return json.dumps({"by": "xpath", "value": f"//*[@{attr}={_xpath_literal(value)}]"})


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
    Maps synthetic visual refs (ocr://, vision://) to something executable.

    Deterministic mapping first (Phase 13I): never execute a synthetic ref
    directly; instead translate it to an existing web/mobile element ref via
    metadata (text / role / content-desc / resource-id). No screenshots or
    provider calls.

    X3 coordinate fallback: when no deterministic element mapping exists and the
    caller opted in (``intent.context["coordinate_click_fallback"]``), a
    click/tap target with a usable bounding box is hydrated to a ``point://x,y``
    coordinate ref so canvas / image-only / custom-drawn UIs are still
    actionable. Off by default — a blind coordinate click is riskier than an
    element click.
    """

    def hydrate(self, *, target: ResolvedTarget, intent: StepIntent) -> HydrationResult:
        deterministic = self._hydrate_deterministic(target=target, intent=intent)
        if deterministic.status == "hydrated" or not is_visual_ref(target.ref):
            return deterministic
        # Deterministic mapping failed for a real visual ref — try the opt-in
        # coordinate fallback before giving up.
        fallback = self._coordinate_fallback(
            target=target, intent=intent, deterministic=deterministic
        )
        return fallback if fallback is not None else deterministic

    def _hydrate_deterministic(self, *, target: ResolvedTarget, intent: StepIntent) -> HydrationResult:
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

        metadata = _safe_metadata(dict(target.metadata))

        if intent.channel == "mobile":
            return self._hydrate_mobile(target=target, ref=ref, metadata=metadata, intent=intent)
        if intent.channel != "web":
            return HydrationResult(
                status="not_hydrated",
                target=None,
                reason="unsupported_visual_ref_hydration",
                diagnostics={"channel": intent.channel},
                original_ref=ref,
                hydrated_ref=None,
            )

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
                diagnostics={"source": "ocr", "strategy": "text", "channel": intent.channel},
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
                diagnostics={"source": "vision", "strategy": strategy, "channel": intent.channel},
                original_ref=ref,
                hydrated_ref=hydrated_target.ref,
            )

        return self._failsafe(ref=ref, scheme="unknown")

    def _hydrate_mobile(
        self,
        *,
        target: ResolvedTarget,
        ref: str,
        metadata: dict[str, Any],
        intent: StepIntent,
    ) -> HydrationResult:
        hierarchy_xml = intent.context.get("hierarchy_xml")
        if not isinstance(hierarchy_xml, str) or not hierarchy_xml.strip():
            return HydrationResult(
                status="not_hydrated",
                target=None,
                reason="mobile_visual_hydration_no_hierarchy",
                diagnostics={"channel": intent.channel},
                original_ref=ref,
                hydrated_ref=None,
            )

        if ref.startswith("ocr://"):
            source = "ocr"
            lookup = _pick_text(metadata, "matched_text", "text")
        elif ref.startswith("vision://"):
            source = "vision"
            lookup = _pick_text(metadata, "matched_text", "label", "text")
        else:
            return self._failsafe(ref=ref, scheme="unknown")

        if not lookup:
            return HydrationResult(
                status="not_hydrated",
                target=None,
                reason="mobile_visual_hydration_unsupported_metadata",
                diagnostics={"source": source},
                original_ref=ref,
                hydrated_ref=None,
            )

        try:
            root = ET.fromstring(hierarchy_xml)
        except ET.ParseError:
            return HydrationResult(
                status="not_hydrated",
                target=None,
                reason="mobile_visual_hydration_invalid_hierarchy",
                diagnostics={"source": source},
                original_ref=ref,
                hydrated_ref=None,
            )

        priorities: list[tuple[str, str, str]] = [
            ("text", "text", "mobile_text"),
            ("content-desc", "content-desc", "mobile_content_desc"),
            ("resource-id", "resource-id", "mobile_resource_id"),
        ]
        for xml_attr, xpath_attr, strategy in priorities:
            matches = [el for el in root.iter() if (el.get(xml_attr) or "").strip() == lookup]
            if len(matches) == 1:
                hydrated_ref = _xpath_ref_for_attr(xpath_attr, lookup)
                hydrated_target = self._hydrated_target(
                    target=target,
                    hydrated_ref=hydrated_ref,
                    source=source,
                    strategy=strategy,
                    metadata=metadata,
                )
                return HydrationResult(
                    status="hydrated",
                    target=hydrated_target,
                    reason="hydrated_mobile_visual_ref",
                    diagnostics={"source": source, "strategy": strategy, "match_field": xml_attr, "channel": intent.channel},
                    original_ref=ref,
                    hydrated_ref=hydrated_ref,
                )
            if len(matches) > 1:
                return HydrationResult(
                    status="not_hydrated",
                    target=None,
                    reason="mobile_visual_hydration_ambiguous_match",
                    diagnostics={
                        "source": source,
                        "match_field": xml_attr,
                        "match_count": len(matches),
                        "channel": intent.channel,
                    },
                    original_ref=ref,
                    hydrated_ref=None,
                )

        return HydrationResult(
            status="not_hydrated",
            target=None,
            reason="mobile_visual_hydration_no_match",
            diagnostics={"source": source, "match_count": 0, "channel": intent.channel},
            original_ref=ref,
            hydrated_ref=None,
        )

    def _coordinate_fallback(
        self,
        *,
        target: ResolvedTarget,
        intent: StepIntent,
        deterministic: HydrationResult,
    ) -> HydrationResult | None:
        """X3: hydrate to a ``point://x,y`` ref from the target's bounding box.

        Returns ``None`` (decline the fallback, keep the deterministic failure)
        unless every guard passes: the fallback is enabled, the action is a
        click/tap, and the target carries a usable bbox. Channel-agnostic — the
        web and mobile adapters both know how to click a coordinate.
        """
        if not intent.context.get("coordinate_click_fallback"):
            return None
        action = str(getattr(intent, "action_type", "") or "").strip().lower()
        if action not in COORDINATE_CLICK_ACTIONS:
            return None
        center = bbox_center(target.metadata.get("bbox"))
        if center is None:
            return None

        x, y = center
        ref = target.ref
        source = "vision" if ref.startswith("vision://") else "ocr"
        hydrated_target = self._hydrated_target(
            target=target,
            hydrated_ref=coordinate_ref(x, y),
            source=source,
            strategy="coordinate",
            metadata=_safe_metadata(dict(target.metadata)),
        )
        enriched = dict(hydrated_target.metadata)
        enriched["coordinate_point"] = [x, y]
        enriched["coordinate_fallback_reason"] = deterministic.reason
        # X3: dispatch is on the structured point, not the ref string. The ref
        # stays a readable point://x,y label for traces/reports.
        hydrated_target = hydrated_target.model_copy(
            update={"metadata": _safe_metadata(enriched), "point": [x, y]}
        )
        return HydrationResult(
            status="hydrated",
            target=hydrated_target,
            reason="hydrated_coordinate_fallback",
            diagnostics={
                "source": source,
                "strategy": "coordinate",
                "channel": intent.channel,
                "point": [x, y],
                "deterministic_reason": deterministic.reason,
            },
            original_ref=ref,
            hydrated_ref=hydrated_target.ref,
        )

    def _failsafe(self, *, ref: str, scheme: str) -> HydrationResult:
        return HydrationResult(
            status="not_hydrated",
            target=None,
            reason="unsupported_visual_ref_hydration",
            diagnostics={"source": scheme},
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
        return target.model_copy(update={"ref": hydrated_ref, "metadata": _safe_metadata(enriched_metadata)})
