"""Phase 19C: internal normalized cross-platform element model (MVP)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field


_BOUNDS_PATTERN = re.compile(r"\[(?P<x1>-?\d+),(?P<y1>-?\d+)\]\[(?P<x2>-?\d+),(?P<y2>-?\d+)\]")


class NormalizedBounds(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def from_appium_bounds(cls, raw: str | None) -> "NormalizedBounds":
        if not raw:
            return cls()
        match = _BOUNDS_PATTERN.fullmatch(raw.strip())
        if not match:
            return cls()
        x1 = int(match.group("x1"))
        y1 = int(match.group("y1"))
        x2 = int(match.group("x2"))
        y2 = int(match.group("y2"))
        return cls(
            x=max(0, x1),
            y=max(0, y1),
            width=max(0, x2 - x1),
            height=max(0, y2 - y1),
        )


class NormalizedElement(BaseModel):
    id: str
    channel: str
    platform: str
    source_kind: str
    source_ref: str | None = None

    role: str | None = None
    tag: str | None = None
    widget_type: str | None = None
    text: str | None = None
    label: str | None = None
    placeholder: str | None = None
    accessibility_name: str | None = None
    content_desc: str | None = None
    resource_id: str | None = None
    test_id: str | None = None

    bounds: NormalizedBounds | None = None
    visible: bool = True
    enabled: bool = True
    selected: bool = False

    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json_safe_dict(self) -> dict[str, Any]:
        """JSON-safe serialization without raw bytes/provider payloads."""
        return self.model_dump(mode="json", exclude_none=True)


def _stable_id(seed: dict[str, Any]) -> str:
    encoded = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]


def normalize_web_entry(entry: dict[str, Any], *, source_kind: str = "accessibility_tree") -> NormalizedElement:
    role = entry.get("role")
    tag = entry.get("tag")
    label = entry.get("label")
    text = entry.get("text")
    accessibility_name = entry.get("accessibility_name") or entry.get("name")
    test_id = entry.get("test_id") or entry.get("data-testid")
    source_ref = entry.get("source_ref") or entry.get("selector")

    seed = {
        "channel": "web",
        "source_kind": source_kind,
        "source_ref": source_ref,
        "role": role,
        "tag": tag,
        "label": label,
        "text": text,
        "test_id": test_id,
    }
    element_id = entry.get("id") or _stable_id(seed)

    return NormalizedElement(
        id=element_id,
        channel="web",
        platform="web",
        source_kind=source_kind,
        source_ref=source_ref,
        role=role,
        tag=tag,
        widget_type=entry.get("widget_type"),
        text=text,
        label=label,
        placeholder=entry.get("placeholder"),
        accessibility_name=accessibility_name,
        test_id=test_id,
        visible=bool(entry.get("visible", True)),
        enabled=bool(entry.get("enabled", True)),
        selected=bool(entry.get("selected", False)),
        parent_id=entry.get("parent_id"),
        children_ids=list(entry.get("children_ids", [])),
        attributes=dict(entry.get("attributes", {})),
        metadata=dict(entry.get("metadata", {})),
    )


def normalize_mobile_hierarchy_node(
    node: dict[str, Any],
    *,
    platform: str = "android",
    source_kind: str = "appium_hierarchy",
) -> NormalizedElement:
    widget_type = node.get("class") or node.get("widget_type")
    text = node.get("text")
    content_desc = node.get("content-desc") or node.get("content_desc")
    resource_id = node.get("resource-id") or node.get("resource_id")
    source_ref = node.get("source_ref") or node.get("xpath")

    seed = {
        "channel": "mobile",
        "platform": platform,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "widget_type": widget_type,
        "text": text,
        "content_desc": content_desc,
        "resource_id": resource_id,
    }
    element_id = node.get("id") or _stable_id(seed)

    bounds = node.get("bounds")
    normalized_bounds = (
        bounds if isinstance(bounds, NormalizedBounds) else NormalizedBounds.from_appium_bounds(bounds)
    )

    return NormalizedElement(
        id=element_id,
        channel="mobile",
        platform=platform,
        source_kind=source_kind,
        source_ref=source_ref,
        role=node.get("role"),
        tag=node.get("tag"),
        widget_type=widget_type,
        text=text,
        label=node.get("label"),
        placeholder=node.get("hint") or node.get("placeholder"),
        accessibility_name=node.get("accessibility_name"),
        content_desc=content_desc,
        resource_id=resource_id,
        test_id=node.get("test_id"),
        bounds=normalized_bounds,
        visible=bool(node.get("displayed", node.get("visible", True))),
        enabled=bool(node.get("enabled", True)),
        selected=bool(node.get("selected", False)),
        parent_id=node.get("parent_id"),
        children_ids=list(node.get("children_ids", [])),
        attributes=dict(node.get("attributes", {})),
        metadata=dict(node.get("metadata", {})),
    )
