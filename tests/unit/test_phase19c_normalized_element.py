from __future__ import annotations

import json

from bubblegum.core.elements.normalized import (
    NormalizedBounds,
    NormalizedElement,
    normalize_mobile_hierarchy_node,
    normalize_web_entry,
)


def test_normalized_element_defaults() -> None:
    element = NormalizedElement(
        id="el-1",
        channel="web",
        platform="web",
        source_kind="accessibility_tree",
    )
    assert element.visible is True
    assert element.enabled is True
    assert element.selected is False
    assert element.children_ids == []
    assert element.attributes == {}
    assert element.metadata == {}


def test_json_safe_serialization() -> None:
    element = NormalizedElement(
        id="el-2",
        channel="mobile",
        platform="android",
        source_kind="appium_hierarchy",
        attributes={"state": "ok", "score": 1},
        metadata={"phase": "19C"},
        bounds=NormalizedBounds(x=10, y=20, width=30, height=40),
    )
    payload = element.to_json_safe_dict()
    assert payload["id"] == "el-2"
    assert payload["bounds"] == {"x": 10, "y": 20, "width": 30, "height": 40}
    json.dumps(payload)


def test_normalize_web_entry() -> None:
    raw = {
        "role": "button",
        "tag": "button",
        "text": "Submit",
        "label": "Submit Order",
        "placeholder": None,
        "name": "Submit",
        "data-testid": "submit-btn",
        "selector": 'role=button[name="Submit"]',
        "visible": True,
        "enabled": True,
        "selected": False,
        "parent_id": "form-1",
        "children_ids": ["icon-1"],
        "attributes": {"aria-expanded": "false"},
        "metadata": {"source": "fixture"},
    }
    element = normalize_web_entry(raw)
    assert element.channel == "web"
    assert element.platform == "web"
    assert element.role == "button"
    assert element.test_id == "submit-btn"
    assert element.accessibility_name == "Submit"
    assert element.parent_id == "form-1"
    assert element.children_ids == ["icon-1"]


def test_normalize_mobile_hierarchy_node() -> None:
    raw = {
        "class": "android.widget.Button",
        "text": "Continue",
        "content-desc": "Continue",
        "resource-id": "com.example:id/continue",
        "xpath": "//android.widget.Button[1]",
        "bounds": "[10,20][110,220]",
        "displayed": True,
        "enabled": False,
        "selected": True,
        "parent_id": "root-1",
        "children_ids": [],
        "attributes": {"index": "0"},
        "metadata": {"origin": "xml"},
    }
    element = normalize_mobile_hierarchy_node(raw)
    assert element.channel == "mobile"
    assert element.platform == "android"
    assert element.widget_type == "android.widget.Button"
    assert element.content_desc == "Continue"
    assert element.resource_id == "com.example:id/continue"
    assert element.bounds == NormalizedBounds(x=10, y=20, width=100, height=200)
    assert element.visible is True
    assert element.enabled is False
    assert element.selected is True


def test_bounds_parsing_and_clamping_safety() -> None:
    parsed = NormalizedBounds.from_appium_bounds("[-10,-20][5,5]")
    assert parsed == NormalizedBounds(x=0, y=0, width=15, height=25)
    invalid = NormalizedBounds.from_appium_bounds("bad")
    assert invalid == NormalizedBounds()


def test_parent_children_and_safe_attrs_metadata() -> None:
    element = normalize_mobile_hierarchy_node(
        {
            "id": "node-5",
            "parent_id": "node-1",
            "children_ids": ["node-6", "node-7"],
            "attributes": {"checked": "true"},
            "metadata": {"hint": "deterministic"},
        }
    )
    assert element.id == "node-5"
    assert element.parent_id == "node-1"
    assert element.children_ids == ["node-6", "node-7"]
    assert element.attributes == {"checked": "true"}
    assert element.metadata == {"hint": "deterministic"}
