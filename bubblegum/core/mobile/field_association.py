"""Mobile label→input and clickable-ancestor association (generic).

Two grounding refinements that matter on real apps regardless of the tech stack:

* **Type into a labelled field.** A field's visible label is very often a
  separate, non-editable node sitting next to the input — React Native and
  native Android/iOS forms, Compose, Flutter-with-semantics all do this. So
  `Enter "…" into "NRIC or FIN"` must target the *input* associated with the
  label "NRIC or FIN", not the label text node (which can't accept text). Without
  this, grounding matches the label, typing fails, and the step stalls.
* **Tap a labelled control.** The node carrying the visible text is frequently
  not the clickable one — the clickable is an ancestor View/Button. Tapping the
  nearest clickable ancestor is more reliable than the bare text node.

Both are pure functions over the Appium hierarchy XML that return an executable
JSON xpath ref (or ``None``). No Appium, no device — fully unit-testable. Used as
a mobile grounding fallback when name-based grounding can't pin the element.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

_EDITABLE_HINTS = (
    "edittext", "textfield", "securetextfield", "autocompletetextview",
    "textinput", "searchfield", "textview.*edit",  # last is defensive, rarely used
)
_TYPE_ACTIONS = frozenset({"type", "fill", "enter", "set", "input"})
_TAP_ACTIONS = frozenset({"tap", "click", "press", "select"})
# Words that describe the *kind* of control, not its label — stripped so
# "NRIC or FIN input field" keys on "nric or fin".
_FIELD_STOPWORDS = frozenset({
    "the", "a", "an", "input", "field", "text", "box", "textbox", "into",
    "enter", "type", "fill", "set", "your", "please",
})
_TEXT_LIKE_ATTRS = frozenset({"text", "content-desc", "label", "name", "value"})
_MAX_CONTAINER_CLIMB = 3


def _norm(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _label_key(phrase: str | None) -> str:
    return " ".join(t for t in _norm(phrase).split() if t not in _FIELD_STOPWORDS)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in parts) + ")"


def _ref(tag: str, attr: str, value: str) -> str:
    tag = tag or "*"
    if attr in _TEXT_LIKE_ATTRS:
        norm = " ".join(value.split())
        expr = f"//{tag}[normalize-space(@{attr})={_xpath_literal(norm)}]"
    else:
        expr = f"//{tag}[@{attr}={_xpath_literal(value)}]"
    return json.dumps({"by": "xpath", "value": expr})


def _is_ios_root(root: ET.Element, platform: str) -> bool:
    if (platform or "").lower() == "ios":
        return True
    tag = (root.tag or "").lower()
    return "xcui" in tag


def _ios_bounds(node: ET.Element) -> tuple[int, int, int, int] | None:
    try:
        x = int(float(node.get("x", "0") or 0))
        y = int(float(node.get("y", "0") or 0))
        w = int(float(node.get("width", "0") or 0))
        h = int(float(node.get("height", "0") or 0))
    except (TypeError, ValueError):
        return None
    if w <= 0 and h <= 0:
        return None
    return (x, y, x + w, y + h)


_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _android_bounds(node: ET.Element) -> tuple[int, int, int, int] | None:
    m = _BOUNDS_RE.match((node.get("bounds") or "").strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


class _View:
    __slots__ = ("cls", "text_attr", "desc_attr", "text", "desc", "rid", "value",
                 "clickable", "editable", "bounds")

    def __init__(self, node: ET.Element, ios: bool) -> None:
        if ios:
            cls = (node.get("type") or node.tag or "").strip()
            self.cls = cls
            self.text_attr, self.desc_attr = "label", "name"
            self.text = (node.get("label") or "").strip()
            self.desc = (node.get("name") or "").strip()
            self.rid = ""
            self.value = (node.get("value") or "").strip()
            self.clickable = cls.lower().endswith(("button", "cell", "link"))
            self.editable = "textfield" in cls.lower()
            self.bounds = _ios_bounds(node)
        else:
            cls = (node.get("class") or node.tag or "").strip()
            self.cls = cls
            self.text_attr, self.desc_attr = "text", "content-desc"
            self.text = (node.get("text") or "").strip()
            self.desc = (node.get("content-desc") or "").strip()
            self.rid = (node.get("resource-id") or "").strip()
            self.value = ""
            self.clickable = (node.get("clickable") or "").strip().lower() == "true"
            self.editable = any(h in cls.lower() for h in _EDITABLE_HINTS)
            self.bounds = _android_bounds(node)

    def best_ref(self) -> str | None:
        """Most stable executable ref for this node: id → a11y desc → text/value."""
        if self.rid:
            return _ref(self.cls, "resource-id", self.rid)
        if self.desc:
            return _ref(self.cls, self.desc_attr, self.desc)
        if self.text:
            return _ref(self.cls, self.text_attr, self.text)
        if self.value:
            return _ref(self.cls, "value", self.value)
        return None

    def matches(self, key: str) -> float:
        """How well this node's own name matches ``key`` (0..1)."""
        best = 0.0
        for raw in (self.text, self.desc, self.value, self.rid.split("/")[-1] if self.rid else ""):
            n = _norm(raw)
            if not n:
                continue
            if n == key:
                return 1.0
            if key in n or n in key:
                longer = max(len(n), len(key))
                best = max(best, (min(len(n), len(key)) / longer) if longer else 0.0)
        return best


def _mid_y(bounds: tuple[int, int, int, int] | None) -> int | None:
    return None if bounds is None else (bounds[1] + bounds[3]) // 2


def resolve_field_ref(
    *,
    hierarchy_xml: str | None,
    target_phrase: str | None,
    action_type: str,
    platform: str = "android",
) -> dict[str, Any] | None:
    """Return ``{"ref": <json xpath>, "strategy": ...}`` or ``None``.

    For a type action, associates the label with its input. For a tap action,
    redirects a non-clickable text node to its nearest clickable ancestor.
    """
    if not hierarchy_xml:
        return None
    key = _label_key(target_phrase)
    if not key:
        return None
    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError:
        return None

    ios = _is_ios_root(root, platform)
    # Flatten with parent links and document order.
    nodes: list[ET.Element] = []
    parent: dict[int, ET.Element | None] = {}
    for p in root.iter():
        for ch in list(p):
            parent[id(ch)] = p
    parent[id(root)] = None
    for n in root.iter():
        nodes.append(n)
    views: dict[int, _View] = {id(n): _View(n, ios) for n in nodes}

    action = (action_type or "").strip().lower()
    if action in _TYPE_ACTIONS:
        return _resolve_type(nodes, parent, views, key)
    if action in _TAP_ACTIONS:
        return _resolve_tap(nodes, parent, views, key)
    return None


def _resolve_type(nodes, parent, views, key) -> dict[str, Any] | None:
    # 1) A self-labelled editable (its own name matches the label).
    best_self = None
    best_self_score = 0.0
    for n in nodes:
        v = views[id(n)]
        if not v.editable:
            continue
        s = v.matches(key)
        if s > best_self_score:
            best_self_score, best_self = s, v
    if best_self is not None and best_self_score >= 0.9:
        ref = best_self.best_ref()
        if ref:
            return {"ref": ref, "strategy": "editable_self_label"}

    # 2) Find the best-matching label node, then the nearest editable to it.
    label_node = None
    label_score = 0.0
    for n in nodes:
        v = views[id(n)]
        if v.editable:
            continue
        s = v.matches(key)
        if s > label_score:
            label_score, label_node = s, n
    if label_node is None or label_score < 0.6:
        # Fall back to any self-labelled editable even at lower confidence.
        if best_self is not None and best_self_score >= 0.6:
            ref = best_self.best_ref()
            if ref:
                return {"ref": ref, "strategy": "editable_self_label"}
        return None

    label_view = views[id(label_node)]
    editable = _nearest_editable_to(label_node, parent, views, nodes)
    if editable is None:
        return None
    ref = views[id(editable)].best_ref()
    if not ref:
        return None
    return {"ref": ref, "strategy": "label_to_input", "label": label_view.text or label_view.desc}


def _nearest_editable_to(label_node, parent, views, nodes) -> ET.Element | None:
    """Nearest editable node to ``label_node``: same container first, then by
    vertical proximity below the label."""
    # Climb up to N container levels; return the closest editable descendant.
    ancestor = label_node
    seen: set[int] = set()
    for _ in range(_MAX_CONTAINER_CLIMB + 1):
        if ancestor is None:
            break
        editables = [d for d in ancestor.iter() if views[id(d)].editable]
        if editables:
            return _closest_below(label_node, editables, views)
        ancestor = parent.get(id(ancestor))
        if ancestor is None or id(ancestor) in seen:
            break
        seen.add(id(ancestor))

    # Whole-screen fallback: the editable directly below the label, closest.
    editables = [d for d in nodes if views[id(d)].editable]
    if editables:
        return _closest_below(label_node, editables, views)
    return None


def _closest_below(label_node, editables, views) -> ET.Element | None:
    lb = views[id(label_node)].bounds
    ly = _mid_y(lb)
    # Prefer an editable whose vertical centre is at/below the label, nearest.
    scored: list[tuple[int, int, ET.Element]] = []
    for idx, e in enumerate(editables):
        ey = _mid_y(views[id(e)].bounds)
        if ly is None or ey is None:
            scored.append((1, idx, e))  # unknown geometry → document order
        else:
            below = ey >= ly
            dist = abs(ey - ly)
            # below-and-near ranks first (0), then above, then farther.
            scored.append((0 if below else 2, dist, e))
    scored.sort(key=lambda t: (t[0], t[1]))
    return scored[0][2] if scored else None


def _resolve_tap(nodes, parent, views, key) -> dict[str, Any] | None:
    # Best-matching visible node for the phrase.
    match_node = None
    match_score = 0.0
    for n in nodes:
        s = views[id(n)].matches(key)
        if s > match_score:
            match_score, match_node = s, n
    if match_node is None or match_score < 0.6:
        return None
    v = views[id(match_node)]
    if v.clickable:
        return None  # normal grounding already handles a clickable match
    # Walk up to the nearest clickable ancestor.
    anc = parent.get(id(match_node))
    hops = 0
    while anc is not None and hops <= _MAX_CONTAINER_CLIMB + 2:
        av = views[id(anc)]
        if av.clickable:
            ref = av.best_ref()
            if ref:
                return {"ref": ref, "strategy": "clickable_ancestor"}
            return None
        anc = parent.get(id(anc))
        hops += 1
    return None
