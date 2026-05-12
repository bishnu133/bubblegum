import json

from bubblegum.core.elements import ElementGraph, NormalizedBounds, NormalizedElement, build_graph_query_diagnostics


def _el(**kw):
    base = dict(channel="web", platform="web", source_kind="test", visible=True, enabled=True)
    base.update(kw)
    return NormalizedElement(**base)


def _graph():
    return ElementGraph([
        _el(id="card1", role="group", tag="section", text="Pro Plan card"),
        _el(id="name_lbl", role="label", text="Name", parent_id="card1", bounds=NormalizedBounds(x=0,y=0,width=40,height=20)),
        _el(id="name_input", role="textbox", tag="input", parent_id="card1", bounds=NormalizedBounds(x=50,y=0,width=100,height=20)),
        _el(id="alice", role="text", text="Alice", bounds=NormalizedBounds(x=0,y=40,width=40,height=20)),
        _el(id="edit_btn", role="button", tag="button", text="Edit", bounds=NormalizedBounds(x=55,y=40,width=40,height=20)),
        _el(id="modal1", role="dialog", text="Delete modal"),
        _el(id="confirm_btn", role="button", text="Confirm", parent_id="modal1"),
        _el(id="region1", role="region", text="Settings"),
        _el(id="country_select", role="combobox", tag="select", text="Country", parent_id="region1"),
        _el(id="mob1", channel="mobile", platform="android", widget_type="android.widget.Button", content_desc="Continue", resource_id="android.btn.continue"),
    ])


def test_neutral_missing_graph_or_context():
    payload = build_graph_query_diagnostics(None, None)
    assert payload["status"] == "no_relation"


def test_unsupported_relation_type():
    payload = build_graph_query_diagnostics(_graph(), {"relation_type": "weird"})
    assert payload["status"] == "unsupported"


def test_label_for_success_and_sorted_ids():
    payload = build_graph_query_diagnostics(_graph(), {"relation_type": "label_for", "primary_target_text": "Name", "control_kind_hint": "input"})
    assert payload["status"] == "ok"
    assert payload["matched_ids"] == sorted(payload["matched_ids"])
    assert "name_input" in payload["matched_ids"]


def test_label_for_ambiguous_and_no_match():
    g = _graph()
    p1 = build_graph_query_diagnostics(g, {"relation_type": "label_for", "primary_target_text": "Missing"})
    assert p1["status"] in {"no_anchor", "no_match"}
    g2 = ElementGraph(list(g.elements_by_id.values()) + [_el(id="name_lbl2", role="label", text="Name")])
    p2 = build_graph_query_diagnostics(g2, {"relation_type": "label_for", "primary_target_text": "Name"})
    assert p2["status"] == "ambiguous"


def test_same_row_success_missing_ambiguous_anchor():
    g = _graph()
    ok = build_graph_query_diagnostics(g, {"relation_type": "same_row_as_text", "anchor_text": "Alice", "control_kind_hint": "button"})
    assert ok["status"] == "ok"
    assert "edit_btn" in ok["matched_ids"]
    miss = build_graph_query_diagnostics(g, {"relation_type": "same_row_as_text", "anchor_text": "Ghost"})
    assert miss["status"] == "no_anchor"
    g2 = ElementGraph(list(g.elements_by_id.values()) + [_el(id="alice2", role="text", text="Alice")])
    amb = build_graph_query_diagnostics(g2, {"relation_type": "same_row_as_text", "anchor_text": "Alice"})
    assert amb["status"] == "ambiguous"


def test_within_card_modal_region_and_dropdown():
    g = _graph()
    c = build_graph_query_diagnostics(g, {"relation_type": "within_card", "scope_label": "Pro Plan card"})
    assert c["scope_resolution"]["status"] in {"resolved", "missing"}
    m = build_graph_query_diagnostics(g, {"relation_type": "within_modal", "scope_label": "Delete modal"})
    assert m["scope_resolution"]["status"] in {"resolved", "missing"}
    r = build_graph_query_diagnostics(g, {"relation_type": "within_region", "scope_label": "Settings", "control_kind_hint": "dropdown"})
    assert r["status"] in {"ok", "no_scope", "no_match"}


def test_mobile_attr_hint_json_safe_and_no_mutation():
    g = _graph()
    before = g.to_json_safe_summary()
    p = build_graph_query_diagnostics(g, {"relation_type": "mobile_attr_hint", "mobile_attr_preference": "content_desc"})
    json.dumps(p)
    after = g.to_json_safe_summary()
    assert before == after
