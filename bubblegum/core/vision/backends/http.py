"""
bubblegum/core/vision/backends/http.py
======================================
HTTPGroundingProvider — self-hosted screenshot-grounding backend (Task #6).

The enterprise / data-residency seam: point Bubblegum at a grounding model you
run **inside your own network** (OmniParser, UI-TARS, a custom VLM service) and
screenshots never leave your infrastructure. No per-call vendor cost, no third
party. It is a plain VisionProvider, so it drops straight into the existing
screenshot -> candidates -> hydrate-to-durable-ref -> cache pipeline.

Contract (POST JSON to the endpoint):
    {"instruction": "<nl step>", "image_base64": "<png b64>", "channel": "...",
     "platform": "...", "mode": "ground"}

The response is normalized from any of three common shapes so a broad range of
self-hosted servers work without a bespoke adapter:

  1. Standard candidates (Bubblegum-native):
       {"candidates": [{"label","role","text","bbox":[x1,y1,x2,y2],"confidence"}]}

  2. Set-of-mark / element enumeration (OmniParser-style):
       {"elements": [{"bbox"|"bounds"|"box", "content"|"caption"|"label", "type"|"role"}]}
     Each enumerated element becomes a candidate — the enumeration *is* the set
     of marks, so no on-image overlay is needed.

  3. Point grounding (UI-TARS / computer-use-style):
       {"point": [x, y]}  or  {"x": .., "y": ..}
     Becomes a single centered candidate. Point-only results need
     grounding.coordinate_click_fallback to act (a pixel is not a durable
     locator); labeled results (shapes 1-2) hydrate to durable role=/text= refs
     and are cached like any other resolution.

Fail-safe: any transport/parse error returns [] with a sanitized diagnostic via
get_last_diagnostic(), so a flaky grounder degrades to the other tiers instead
of breaking a run. stdlib-only (urllib) — no new dependency.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any

from bubblegum.core.vision.engine import VisionCandidate, normalize_vision_candidates


class HTTPGroundingProvider:
    """VisionProvider backed by a self-hosted HTTP grounding service."""

    provider_name = "http_grounding"

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        transport: Any | None = None,
    ) -> None:
        if not endpoint or not str(endpoint).strip():
            raise ValueError("HTTPGroundingProvider requires a non-empty endpoint URL.")
        self._endpoint = str(endpoint).strip()
        self._timeout = float(timeout)
        self._headers = {"Content-Type": "application/json", **(headers or {})}
        # transport(url, data_bytes, headers, timeout) -> response_text.
        # Injectable so tests (and alternative HTTP stacks) need no real socket.
        self._transport = transport or _urllib_post
        self.last_diagnostic: dict[str, Any] | None = None

    def get_last_diagnostic(self) -> dict[str, Any] | None:
        return self.last_diagnostic

    def detect_targets(
        self,
        image_bytes: bytes,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> list[VisionCandidate]:
        self.last_diagnostic = None
        if not image_bytes:
            self._diag("empty_image", "Screenshot bytes were empty; request skipped.")
            return []

        payload = {
            "instruction": (instruction or "").strip(),
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "mode": "ground",
        }
        if context:
            payload["channel"] = context.get("channel")
            payload["platform"] = context.get("platform")

        try:
            body = json.dumps(payload).encode("utf-8")
            raw = self._transport(self._endpoint, body, self._headers, self._timeout)
        except Exception as exc:  # noqa: BLE001 — never break a run on a grounder hiccup
            self._diag("request_failed", "Grounding endpoint request failed.", exc)
            return []

        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:  # noqa: BLE001
            self._diag("parse_failed", "Grounding response was not valid JSON.", exc)
            return []

        candidates = _normalize_response(parsed)
        if not candidates:
            self._diag("no_candidates", "Grounding response contained no usable candidates.")
        return normalize_vision_candidates(candidates)

    # ------------------------------------------------------------------

    def _diag(self, code: str, message: str, exc: Exception | None = None) -> None:
        d: dict[str, Any] = {"provider": self.provider_name, "code": code, "message": message}
        if exc is not None:
            d["exception_type"] = type(exc).__name__
        self.last_diagnostic = d


# ---------------------------------------------------------------------------
# Response normalization — accept the three common server shapes
# ---------------------------------------------------------------------------

def _normalize_response(parsed: Any) -> list[dict[str, Any]]:
    if not isinstance(parsed, dict):
        return []

    # Shape 1 — native candidates.
    if isinstance(parsed.get("candidates"), list):
        return [_candidate_dict(c) for c in parsed["candidates"] if isinstance(c, dict)]

    # Shape 2 — OmniParser-style element enumeration (set-of-mark).
    if isinstance(parsed.get("elements"), list):
        out: list[dict[str, Any]] = []
        for el in parsed["elements"]:
            if not isinstance(el, dict):
                continue
            label = _first(el, "content", "caption", "label", "text", "name")
            if not label:
                continue
            out.append({
                "label": label,
                "role": _first(el, "type", "role"),
                "text": _first(el, "text", "content", "caption"),
                "bbox": _coerce_bbox(_first_val(el, "bbox", "bounds", "box")),
                "confidence": _coerce_float(el.get("confidence"), 0.7),
            })
        return out

    # Shape 3 — single point (UI-TARS / computer-use).
    point = _extract_point(parsed)
    if point is not None:
        x, y = point
        return [{
            "label": str(parsed.get("label") or "target"),
            "role": parsed.get("role"),
            "text": parsed.get("text"),
            "bbox": [x - 1, y - 1, x + 1, y + 1],
            "confidence": _coerce_float(parsed.get("confidence"), 0.7),
        }]
    return []


def _candidate_dict(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": _first(c, "label", "content", "caption", "text", "name") or "",
        "role": _first(c, "role", "type"),
        "text": _first(c, "text", "content"),
        "bbox": _coerce_bbox(_first_val(c, "bbox", "bounds", "box")),
        "confidence": _coerce_float(c.get("confidence"), 0.7),
    }


def _extract_point(parsed: dict[str, Any]) -> tuple[float, float] | None:
    pt = parsed.get("point")
    if isinstance(pt, (list, tuple)) and len(pt) == 2 and _is_num(pt[0]) and _is_num(pt[1]):
        return float(pt[0]), float(pt[1])
    if _is_num(parsed.get("x")) and _is_num(parsed.get("y")):
        return float(parsed["x"]), float(parsed["y"])
    return None


def _first(d: dict[str, Any], *keys: str) -> str | None:
    """First present non-empty *string* value among keys."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first_val(d: dict[str, Any], *keys: str) -> Any:
    """First present non-None value among keys, of any type (for bbox lists)."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _coerce_bbox(raw: Any) -> list[int] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    if not all(_is_num(v) for v in raw):
        return None
    return [int(v) for v in raw]


def _coerce_float(v: Any, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _urllib_post(url: str, data: bytes, headers: dict[str, str], timeout: float) -> str:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user-configured endpoint
        return resp.read().decode("utf-8")
