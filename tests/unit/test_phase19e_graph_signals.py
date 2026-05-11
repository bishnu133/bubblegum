from __future__ import annotations

import json

from bubblegum.core.elements.graph import ElementGraph
from bubblegum.core.elements.graph_signals import GraphSignalInput, compute_graph_signals
from bubblegum.core.elements.normalized import NormalizedElement
from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def _intent(*, instruction: str, channel: str, platform: str, action_type: str, context: dict) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel=channel,
        platform=platform,
        action_type=action_type,
        context=context,
        options=ExecutionOptions(),
    )


def test_compute_graph_signals_missing_context_safe() -> None:
    payload = compute_graph_signals(
        GraphSignalInput(candidate_ref='text="Login"', instruction="Click Login"),
        graph=None,
        elements_by_ref=None,
    )
    assert payload["reason"] == "no_graph_context"
    assert set(payload.keys()) == {
        "label_for_match",
        "same_row_match",
        "same_container_match",
        "nearby_label_match",
        "role_match_with_graph_context",
        "unique_in_scope",
        "visible_enabled_match",
        "score_hint",
        "reason",
    }


def test_compute_graph_signals_json_safe_compact() -> None:
    label = NormalizedElement(id="l1", channel="mobile", platform="android", source_kind="appium_hierarchy", source_ref='{"by":"xpath","value":"//android.widget.TextView[@text=\'Email\']"}', widget_type="android.widget.TextView", text="Email", bounds={"x": 10, "y": 20, "width": 80, "height": 20})
    field = NormalizedElement(id="f1", channel="mobile", platform="android", source_kind="appium_hierarchy", source_ref='{"by":"xpath","value":"//android.widget.EditText[@content-desc=\'Email input\']"}', widget_type="android.widget.EditText", content_desc="Email input", bounds={"x": 120, "y": 20, "width": 180, "height": 40})
    graph = ElementGraph([label, field])
    by_ref = {label.source_ref: label, field.source_ref: field}
    payload = compute_graph_signals(
        GraphSignalInput(candidate_ref=field.source_ref or "", candidate_text="Email input", candidate_role="textbox", instruction="Type email"),
        graph=graph,
        elements_by_ref=by_ref,
    )
    json.dumps(payload)
    assert isinstance(payload["score_hint"], float)
    assert payload["reason"] == "ok"


def test_accessibility_resolver_emits_graph_signals_without_changing_signals_contract() -> None:
    resolver = AccessibilityTreeResolver()
    snapshot = '\n'.join(['- button "Login"'])
    intent = _intent(
        instruction="Click Login",
        channel="web",
        platform="web",
        action_type="click",
        context={"a11y_snapshot": snapshot},
    )
    candidates = resolver.resolve(intent)
    assert candidates
    meta = candidates[0].metadata
    assert "signals" in meta
    assert "graph_signals" in meta
    assert isinstance(meta["graph_signals"], dict)
    assert candidates[0].confidence == 0.96


def test_appium_resolver_emits_graph_signals_without_confidence_change() -> None:
    resolver = AppiumHierarchyResolver()
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <hierarchy>
      <android.widget.FrameLayout bounds='[0,0][1080,1920]'>
        <android.widget.TextView text='Login' bounds='[100,200][300,260]' />
      </android.widget.FrameLayout>
    </hierarchy>"""
    intent = _intent(
        instruction="Tap Login",
        channel="mobile",
        platform="android",
        action_type="tap",
        context={"hierarchy_xml": xml},
    )
    candidates = resolver.resolve(intent)
    assert candidates
    meta = candidates[0].metadata
    assert "signals" in meta
    assert "graph_signals" in meta
    assert candidates[0].confidence == 0.92
