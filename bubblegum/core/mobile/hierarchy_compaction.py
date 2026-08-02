"""Hierarchy compaction for mobile grounding (M-E).

On a complex app ``driver.page_source`` can be thousands of nodes — mostly
decorative layout containers with no text, no id, and nothing to interact with.
The hierarchy resolver parses and builds a graph over *every* node on every
grounding pass (and again on each scroll re-ground), so that bulk is pure
latency — and on a device farm, latency near the command timeout is a
reliability risk.

This module prunes the hierarchy down to the nodes that can actually be a
grounding target — anything carrying text / a11y description / id / value, plus
interactive and scrollable nodes — and their ancestors. It is **parity-safe by
construction**: every node that could produce a candidate is kept, and the
resolver builds its locators as global XPaths (``//tag[@text='…']``) that don't
depend on the pruned structure, so the *same* candidates resolve — just faster.

Scoped to grounding only. The full ``page_source`` is left untouched for the
readiness / system-dialog / framework detectors, which rely on nodes (progress
bars, dialog containers) that compaction would legitimately drop.

Pure and side-effect free — no Appium, no device.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

# Attributes that make a node a possible grounding target (visible text / a11y).
_TEXT_ATTRS: tuple[str, ...] = ("text", "content-desc", "label", "value", "name")
# Any of these + resource-id make a node "groundable".
_GROUNDABLE_ATTRS: tuple[str, ...] = _TEXT_ATTRS + ("resource-id",)
# Class/type substrings that mark an interactive control worth keeping even when
# it has no text of its own (icon buttons, switches, cells, …).
_INTERACTIVE_HINTS: tuple[str, ...] = (
    "button", "edittext", "textfield", "securetextfield", "checkbox", "switch",
    "image", "cell", "link", "radiobutton", "seekbar", "spinner", "tab",
)


def _has_text(node: ET.Element) -> bool:
    return any((node.get(a) or "").strip() for a in _TEXT_ATTRS)


def _is_groundable(node: ET.Element) -> bool:
    if any((node.get(a) or "").strip() for a in _GROUNDABLE_ATTRS):
        return True
    if (node.get("clickable") or "").strip().lower() == "true":
        return True
    if (node.get("scrollable") or "").strip().lower() == "true":
        return True
    cls = (node.get("class") or node.tag or "").lower()
    return any(hint in cls for hint in _INTERACTIVE_HINTS)


def _is_invisible(node: ET.Element) -> bool:
    if (node.get("visible-to-user") or "").strip().lower() == "false":
        return True
    if (node.get("visible") or "").strip().lower() == "false":
        return True
    if (node.get("hidden") or "").strip().lower() in ("true", "1"):
        return True
    bounds = (node.get("bounds") or "").strip()
    return bounds == "[0,0][0,0]"


def compact_hierarchy_xml(
    xml: str | None,
    *,
    max_nodes: int = 1500,
    drop_invisible: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Prune a hierarchy XML to its groundable nodes (and their ancestors).

    Returns ``(compacted_xml, stats)``. ``stats`` reports ``original_nodes``,
    ``kept_nodes``, ``dropped_nodes``, ``compacted`` (whether anything changed)
    and ``truncated`` (kept still exceeds ``max_nodes`` — advisory; no groundable
    node is ever dropped to meet the cap, so candidate parity is guaranteed).
    On empty or unparseable input the original string is returned unchanged.
    """
    stats: dict[str, Any] = {
        "original_nodes": 0,
        "kept_nodes": 0,
        "dropped_nodes": 0,
        "compacted": False,
        "truncated": False,
    }
    if not xml or not xml.strip():
        return xml or "", stats
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        stats["parse_error"] = True
        return xml, stats

    original = sum(1 for _ in root.iter())
    stats["original_nodes"] = original

    # Post-order: a node is kept if it is groundable itself or has a kept
    # descendant. Invisible textless nodes are treated as not groundable.
    keep: dict[int, bool] = {}

    def _visit(node: ET.Element) -> bool:
        child_kept = False
        for child in list(node):
            child_kept = _visit(child) or child_kept
        useful = _is_groundable(node)
        if useful and drop_invisible and _is_invisible(node) and not _has_text(node):
            useful = False
        kept = useful or child_kept
        keep[id(node)] = kept
        return kept

    _visit(root)
    keep[id(root)] = True  # never drop the root

    def _prune(node: ET.Element) -> None:
        for child in list(node):
            if keep.get(id(child)):
                _prune(child)
            else:
                node.remove(child)

    _prune(root)

    kept = sum(1 for _ in root.iter())
    stats["kept_nodes"] = kept
    stats["dropped_nodes"] = max(0, original - kept)
    stats["compacted"] = kept < original
    stats["truncated"] = kept > max_nodes

    if not stats["compacted"]:
        # Nothing removed — return the original text to avoid a needless reserialize.
        return xml, stats
    return ET.tostring(root, encoding="unicode"), stats
