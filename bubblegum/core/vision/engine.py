from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class VisionCandidate:
    label: str
    bbox: list[int] | tuple[int, int, int, int] | None
    confidence: float
    role: str | None = None
    text: str | None = None

class VisionProvider(Protocol):
    def detect_targets(self, image_bytes: bytes, instruction: str, context: dict[str, Any] | None = None) -> list[VisionCandidate] | list[dict[str, Any]]: ...

class FakeVisionProvider:
    def detect_targets(self, image_bytes: bytes, instruction: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not image_bytes:
            return []
        hint = (instruction or "").strip() or "target"
        return [{"label": hint, "bbox": [10,20,110,70], "confidence": 0.82, "role": "button", "text": hint}]

def normalize_vision_candidates(candidates: list[VisionCandidate] | list[dict[str, Any]] | None) -> list[VisionCandidate]:
    if not candidates:
        return []
    out: list[VisionCandidate] = []
    for item in candidates:
        c = _coerce_candidate(item)
        if c is not None:
            out.append(c)
    return out

def _coerce_candidate(item: VisionCandidate | dict[str, Any]) -> VisionCandidate | None:
    if isinstance(item, VisionCandidate):
        label = item.label.strip()
        if not label:
            return None
        bbox = _normalize_bbox(item.bbox)
        if item.bbox is not None and bbox is None:
            return None
        return VisionCandidate(label=label,bbox=bbox,confidence=_clamp_confidence(item.confidence),role=_optional_str(item.role),text=_optional_str(item.text))
    if not isinstance(item, dict):
        return None
    raw_label = item.get("label")
    if not isinstance(raw_label, str):
        return None
    label = raw_label.strip()
    if not label:
        return None
    raw_bbox = item.get("bbox")
    bbox = _normalize_bbox(raw_bbox)
    if raw_bbox is not None and bbox is None:
        return None
    return VisionCandidate(label=label,bbox=bbox,confidence=_clamp_confidence(item.get("confidence",0.0)),role=_optional_str(item.get("role")),text=_optional_str(item.get("text")))

def _normalize_bbox(raw: Any) -> list[int] | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    vals: list[int] = []
    for v in raw:
        if isinstance(v, bool) or not isinstance(v, (int,float)):
            return None
        vals.append(int(v))
    return vals

def _clamp_confidence(value: Any) -> float:
    try:
        conf=float(value)
    except Exception:
        conf=0.0
    return 0.0 if conf < 0.0 else 1.0 if conf > 1.0 else conf

def _optional_str(value: Any) -> str | None:
    if value is None or not isinstance(value,str):
        return None
    value=value.strip()
    return value or None

def build_vision_candidates_from_screenshot(screenshot_bytes: bytes | None, *, instruction: str, provider: VisionProvider | None, enabled: bool, privacy_gate: bool, context: dict[str, Any] | None = None) -> list[VisionCandidate]:
    if not enabled or not privacy_gate or not screenshot_bytes or provider is None:
        return []
    try:
        raw = provider.detect_targets(screenshot_bytes, instruction, context=context)
    except Exception:
        return []
    return normalize_vision_candidates(raw)
