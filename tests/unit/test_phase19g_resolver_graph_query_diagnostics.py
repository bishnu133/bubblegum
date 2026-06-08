import json

import pytest

from bubblegum.core.elements import ElementGraph, NormalizedBounds, NormalizedElement
from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def _el(**kw):
    base = dict(channel="web", platform="web", source_kind="test", visible=True, enabled=True)
    base.update(kw)
    return NormalizedElement(**base)


def _web_graph() -> ElementGraph:
    return ElementGraph([
        _el(id="row_name", role="text", text="Alice", bounds=NormalizedBounds(x=0, y=0, width=50, height=20)),
        _el(id="row_btn", role="button", tag="button", text="Edit", bounds=NormalizedBounds(x=60, y=0, width=50, height=20)),
    ])


def test_accessibility_emits_graph_query_diagnostics_when_graph_and_relational_intent_exist():
    resolver = AccessibilityTreeResolver()
    graph = _web_graph()
    intent = StepIntent(
        instruction="Click Edit for Alice",
        channel="web",
        platform="web",
        action_type="click",
        context={
            "a11y_snapshot": '- button "Edit"\n- text "Alice"',
            "element_graph": graph,
            "relational_intent": {"relation_type": "same_row_as_text", "anchor_text": "Alice", "control_kind_hint": "button"},
        },
        options=ExecutionOptions(),
    )
    out = resolver.resolve(intent)
    assert out
    md = out[0].metadata
    assert "graph_query_diagnostics" in md
    gqd = md["graph_query_diagnostics"]
    json.dumps(gqd)
    assert gqd["relation_type"] == "same_row_as_text"
    assert set(gqd.keys()) == {"status", "relation_type", "anchor_resolution", "scope_resolution", "matched_ids", "excluded_ids", "ambiguity", "reasons"}
    assert out[0].ref == 'role=button[name="Edit"]'
    # Phase 22E-1: control_kind_hint=button aligns with role=button, so the
    # resolver applies a small tie-break confidence bias on top of the 0.96
    # text-match score.
    assert out[0].confidence == pytest.approx(0.99, abs=1e-6)
    assert "signals" in md
    assert "graph_signals" in md
    assert "a11y_snapshot" not in json.dumps(gqd)


def test_accessibility_does_not_emit_graph_query_diagnostics_without_required_context():
    resolver = AccessibilityTreeResolver()
    intent = StepIntent(
        instruction="Click Edit",
        channel="web",
        platform="web",
        action_type="click",
        context={"a11y_snapshot": '- button "Edit"'},
        options=ExecutionOptions(),
    )
    out = resolver.resolve(intent)
    assert out
    assert "graph_query_diagnostics" not in out[0].metadata


def test_appium_emits_graph_query_diagnostics_when_graph_and_relational_intent_exist():
    resolver = AppiumHierarchyResolver()
    xml = '<hierarchy><node class="android.widget.TextView" text="Continue" content-desc="" resource-id="" bounds="[0,0][10,10]"/></hierarchy>'
    graph = ElementGraph([
        NormalizedElement(
            id="mob1",
            channel="mobile",
            platform="android",
            source_kind="test",
            role="button",
            text="Continue",
            content_desc="Continue",
            widget_type="android.widget.TextView",
            visible=True,
            enabled=True,
        )
    ])
    intent = StepIntent(
        instruction="Tap Continue",
        channel="mobile",
        platform="android",
        action_type="tap",
        context={
            "hierarchy_xml": xml,
            "graph": graph,
            "relational_intent": {"relation_type": "mobile_attr_hint", "mobile_attr_preference": "content_desc"},
        },
        options=ExecutionOptions(),
    )
    out = resolver.resolve(intent)
    assert out
    md = out[0].metadata
    assert out[0].confidence == 0.92
    assert "graph_query_diagnostics" in md
    gqd = md["graph_query_diagnostics"]
    json.dumps(gqd)
    assert gqd["relation_type"] == "mobile_attr_hint"
    assert "hierarchy_xml" not in json.dumps(gqd)
    assert "graph_signals" in md
    assert "signals" in md


def test_appium_does_not_emit_graph_query_diagnostics_without_required_context():
    resolver = AppiumHierarchyResolver()
    xml = '<hierarchy><node class="android.widget.TextView" text="Continue" content-desc="" resource-id="" bounds="[0,0][10,10]"/></hierarchy>'
    intent = StepIntent(
        instruction="Tap Continue",
        channel="mobile",
        platform="android",
        action_type="tap",
        context={"hierarchy_xml": xml},
        options=ExecutionOptions(),
    )
    out = resolver.resolve(intent)
    assert out
    assert out[0].confidence == 0.92
    assert "graph_query_diagnostics" not in out[0].metadata
