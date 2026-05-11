"""Phase 19D: internal UI Element Graph MVP over normalized elements."""

from __future__ import annotations

from collections import defaultdict

from .normalized import NormalizedBounds, NormalizedElement

_NEARBY_X_GAP = 40
_NEARBY_Y_GAP = 32
_SAME_ROW_VERTICAL_OVERLAP_RATIO = 0.6
_LABEL_MAX_HORIZONTAL_DISTANCE = 300

_INPUT_ROLE_HINTS = frozenset({"textbox", "input", "searchbox", "combobox", "spinbutton", "textarea"})
_INPUT_TAG_HINTS = frozenset({"input", "textarea", "select"})
_INPUT_WIDGET_HINTS = frozenset({"edittext", "textfield", "textinputedittext"})
_LABEL_ROLE_HINTS = frozenset({"label", "text", "statictext"})


class ElementGraph:
    """Deterministic, JSON-safe relationship graph for normalized elements."""

    def __init__(self, elements: list[NormalizedElement]):
        self.elements_by_id: dict[str, NormalizedElement] = {element.id: element for element in elements}
        self.parent_to_children: dict[str, list[str]] = defaultdict(list)
        self.child_to_parent: dict[str, str] = {}
        self.sibling_map: dict[str, list[str]] = defaultdict(list)
        self.nearby_map: dict[str, list[str]] = defaultdict(list)
        self.label_for_map: dict[str, list[str]] = defaultdict(list)
        self.control_to_labels_map: dict[str, list[str]] = defaultdict(list)
        self.same_row_map: dict[str, list[str]] = defaultdict(list)
        self.same_container_map: dict[str, list[str]] = defaultdict(list)

        self._build_hierarchy()
        self._build_siblings()
        self._build_spatial_relationships()
        self._build_label_relationships()
        self._build_same_container()

    def _build_hierarchy(self) -> None:
        for element in self.elements_by_id.values():
            if element.parent_id and element.parent_id in self.elements_by_id:
                self.child_to_parent[element.id] = element.parent_id
                self.parent_to_children[element.parent_id].append(element.id)
            for child_id in element.children_ids:
                if child_id in self.elements_by_id:
                    self.parent_to_children[element.id].append(child_id)
                    self.child_to_parent.setdefault(child_id, element.id)

        for parent, children in list(self.parent_to_children.items()):
            unique = sorted(set(children))
            self.parent_to_children[parent] = unique

    def _build_siblings(self) -> None:
        for _parent_id, children in self.parent_to_children.items():
            for child_id in children:
                siblings = [candidate for candidate in children if candidate != child_id]
                if siblings:
                    self.sibling_map[child_id] = siblings

    def _build_spatial_relationships(self) -> None:
        ids = sorted(self.elements_by_id.keys())
        for i, left_id in enumerate(ids):
            left = self.elements_by_id[left_id]
            for right_id in ids[i + 1 :]:
                right = self.elements_by_id[right_id]
                if self._are_nearby(left.bounds, right.bounds):
                    self.nearby_map[left_id].append(right_id)
                    self.nearby_map[right_id].append(left_id)
                if self._is_same_row(left.bounds, right.bounds):
                    self.same_row_map[left_id].append(right_id)
                    self.same_row_map[right_id].append(left_id)

        for key in list(self.nearby_map):
            self.nearby_map[key] = sorted(set(self.nearby_map[key]))
        for key in list(self.same_row_map):
            self.same_row_map[key] = sorted(set(self.same_row_map[key]))

    def _build_label_relationships(self) -> None:
        labels = [element for element in self.elements_by_id.values() if self._is_label_like(element)]
        controls = [element for element in self.elements_by_id.values() if self._is_input_like(element)]

        for label in sorted(labels, key=lambda e: e.id):
            label_text = self._best_text(label)
            if not label_text:
                continue
            for control in sorted(controls, key=lambda e: e.id):
                if self._label_matches_control(label, control):
                    self.label_for_map[label.id].append(control.id)
                    self.control_to_labels_map[control.id].append(label.id)

        for key in list(self.label_for_map):
            self.label_for_map[key] = sorted(set(self.label_for_map[key]))
        for key in list(self.control_to_labels_map):
            self.control_to_labels_map[key] = sorted(set(self.control_to_labels_map[key]))

    def _build_same_container(self) -> None:
        for element_id in sorted(self.elements_by_id):
            parent_id = self.child_to_parent.get(element_id)
            if not parent_id:
                continue
            peers = [child_id for child_id in self.parent_to_children.get(parent_id, []) if child_id != element_id]
            if peers:
                self.same_container_map[element_id] = sorted(set(peers))

    @staticmethod
    def _are_nearby(left: NormalizedBounds | None, right: NormalizedBounds | None) -> bool:
        if not left or not right:
            return False
        left_right = left.x + left.width
        right_right = right.x + right.width
        left_bottom = left.y + left.height
        right_bottom = right.y + right.height

        dx = max(left.x - right_right, right.x - left_right, 0)
        dy = max(left.y - right_bottom, right.y - left_bottom, 0)
        return dx <= _NEARBY_X_GAP and dy <= _NEARBY_Y_GAP

    @staticmethod
    def _is_same_row(left: NormalizedBounds | None, right: NormalizedBounds | None) -> bool:
        if not left or not right or left.height <= 0 or right.height <= 0:
            return False
        top = max(left.y, right.y)
        bottom = min(left.y + left.height, right.y + right.height)
        overlap = bottom - top
        if overlap <= 0:
            return False
        min_height = min(left.height, right.height)
        return (overlap / min_height) >= _SAME_ROW_VERTICAL_OVERLAP_RATIO

    @staticmethod
    def _best_text(element: NormalizedElement) -> str | None:
        return element.label or element.text or element.accessibility_name or element.content_desc

    @staticmethod
    def _is_label_like(element: NormalizedElement) -> bool:
        role = (element.role or "").lower()
        tag = (element.tag or "").lower()
        widget = (element.widget_type or "").lower()
        return role in _LABEL_ROLE_HINTS or tag == "label" or widget.endswith("textview")

    @staticmethod
    def _is_input_like(element: NormalizedElement) -> bool:
        role = (element.role or "").lower()
        tag = (element.tag or "").lower()
        widget = (element.widget_type or "").lower()
        return role in _INPUT_ROLE_HINTS or tag in _INPUT_TAG_HINTS or any(h in widget for h in _INPUT_WIDGET_HINTS)

    def _label_matches_control(self, label: NormalizedElement, control: NormalizedElement) -> bool:
        if label.id == control.id:
            return False
        if self.child_to_parent.get(label.id) and self.child_to_parent.get(label.id) == self.child_to_parent.get(control.id):
            return True
        if control.id in self.nearby_map.get(label.id, []):
            if self._is_reasonably_left_or_above(label.bounds, control.bounds):
                return True
        return False

    @staticmethod
    def _is_reasonably_left_or_above(left: NormalizedBounds | None, right: NormalizedBounds | None) -> bool:
        if not left or not right:
            return False
        left_edge_distance = right.x - (left.x + left.width)
        above_distance = right.y - (left.y + left.height)
        return (0 <= left_edge_distance <= _LABEL_MAX_HORIZONTAL_DISTANCE) or (0 <= above_distance <= _NEARBY_Y_GAP)

    def get_element(self, element_id: str) -> NormalizedElement | None:
        return self.elements_by_id.get(element_id)

    def children_of(self, element_id: str) -> list[NormalizedElement]:
        return [self.elements_by_id[cid] for cid in self.parent_to_children.get(element_id, []) if cid in self.elements_by_id]

    def parent_of(self, element_id: str) -> NormalizedElement | None:
        parent_id = self.child_to_parent.get(element_id)
        if not parent_id:
            return None
        return self.elements_by_id.get(parent_id)

    def siblings_of(self, element_id: str) -> list[NormalizedElement]:
        return [self.elements_by_id[sid] for sid in self.sibling_map.get(element_id, []) if sid in self.elements_by_id]

    def nearby(self, element_id: str) -> list[NormalizedElement]:
        return [self.elements_by_id[nid] for nid in self.nearby_map.get(element_id, []) if nid in self.elements_by_id]

    def labels_for(self, element_id: str) -> list[NormalizedElement]:
        label_ids = self.control_to_labels_map.get(element_id, [])
        return [self.elements_by_id[label_id] for label_id in label_ids if label_id in self.elements_by_id]

    def controls_for_label(self, label_text: str) -> list[NormalizedElement]:
        needle = label_text.strip().casefold()
        if not needle:
            return []
        controls: list[NormalizedElement] = []
        for label_id, control_ids in self.label_for_map.items():
            label = self.elements_by_id.get(label_id)
            if not label:
                continue
            label_value = (self._best_text(label) or "").strip().casefold()
            if label_value == needle:
                for control_id in control_ids:
                    control = self.elements_by_id.get(control_id)
                    if control:
                        controls.append(control)
        deduped = {element.id: element for element in controls}
        return [deduped[element_id] for element_id in sorted(deduped)]

    def elements_with_text(self, text: str) -> list[NormalizedElement]:
        needle = text.strip().casefold()
        if not needle:
            return []
        result = []
        for element in self.elements_by_id.values():
            haystacks = [element.text, element.label, element.accessibility_name, element.content_desc, element.placeholder]
            if any((value or "").strip().casefold() == needle for value in haystacks):
                result.append(element)
        return sorted(result, key=lambda element: element.id)

    def elements_by_role(self, role: str) -> list[NormalizedElement]:
        needle = role.strip().casefold()
        if not needle:
            return []
        return sorted(
            [element for element in self.elements_by_id.values() if (element.role or "").strip().casefold() == needle],
            key=lambda element: element.id,
        )

    def to_json_safe_summary(self) -> dict[str, object]:
        return {
            "elements": sorted(self.elements_by_id.keys()),
            "relations": {
                "parent": dict(self.child_to_parent),
                "child": dict(self.parent_to_children),
                "sibling": dict(self.sibling_map),
                "nearby": dict(self.nearby_map),
                "label_for": dict(self.label_for_map),
                "same_row": dict(self.same_row_map),
                "same_container": dict(self.same_container_map),
            },
        }
