from __future__ import annotations

import json

from bubblegum.core.elements.graph import ElementGraph
from bubblegum.core.elements.normalized import NormalizedBounds, NormalizedElement


def _el(
    element_id: str,
    *,
    role: str | None = None,
    tag: str | None = None,
    widget_type: str | None = None,
    text: str | None = None,
    label: str | None = None,
    parent_id: str | None = None,
    children_ids: list[str] | None = None,
    bounds: NormalizedBounds | None = None,
) -> NormalizedElement:
    return NormalizedElement(
        id=element_id,
        channel="web",
        platform="web",
        source_kind="accessibility_tree",
        role=role,
        tag=tag,
        widget_type=widget_type,
        text=text,
        label=label,
        parent_id=parent_id,
        children_ids=children_ids or [],
        bounds=bounds,
    )


def test_graph_creation_and_lookup_helpers() -> None:
    elements = [
        _el("root", children_ids=["name-label", "name-input", "save-btn"]),
        _el("name-label", role="label", tag="label", text="Name", parent_id="root", bounds=NormalizedBounds(x=10, y=10, width=80, height=20)),
        _el("name-input", role="textbox", tag="input", parent_id="root", bounds=NormalizedBounds(x=100, y=8, width=150, height=28)),
        _el("save-btn", role="button", text="Save", parent_id="root", bounds=NormalizedBounds(x=10, y=50, width=80, height=24)),
    ]
    graph = ElementGraph(elements)

    assert graph.get_element("name-input") is not None
    assert graph.get_element("missing") is None

    assert [e.id for e in graph.children_of("root")] == ["name-input", "name-label", "save-btn"]
    assert graph.parent_of("name-label") is not None
    assert graph.parent_of("name-label").id == "root"
    assert graph.parent_of("missing") is None

    assert sorted(e.id for e in graph.siblings_of("name-label")) == ["name-input", "save-btn"]
    assert graph.siblings_of("missing") == []


def test_nearby_same_row_and_label_relations() -> None:
    elements = [
        _el("email-label", role="label", tag="label", text="Email", bounds=NormalizedBounds(x=10, y=100, width=70, height=20)),
        _el("email-input", role="textbox", tag="input", bounds=NormalizedBounds(x=90, y=98, width=200, height=26)),
        _el("far-btn", role="button", text="Delete", bounds=NormalizedBounds(x=600, y=400, width=90, height=24)),
    ]
    graph = ElementGraph(elements)

    assert sorted(e.id for e in graph.nearby("email-label")) == ["email-input"]
    assert graph.nearby("missing") == []

    assert sorted(e.id for e in graph.controls_for_label("Email")) == ["email-input"]
    assert sorted(e.id for e in graph.labels_for("email-input")) == ["email-label"]

    same_row = sorted(graph.to_json_safe_summary()["relations"]["same_row"]["email-label"])
    assert same_row == ["email-input"]


def test_role_text_lookup_and_json_safe_summary() -> None:
    elements = [
        _el("status", role="text", text="Active"),
        _el("status-filter", role="combobox", text="Active"),
        _el("other", role="button", text="Edit"),
    ]
    graph = ElementGraph(elements)

    assert [e.id for e in graph.elements_by_role("combobox")] == ["status-filter"]
    assert sorted(e.id for e in graph.elements_with_text("Active")) == ["status", "status-filter"]
    assert graph.elements_by_role("missing") == []
    assert graph.elements_with_text(" ") == []

    summary = graph.to_json_safe_summary()
    json.dumps(summary)
    assert "relations" in summary
    assert "same_container" in summary["relations"]
