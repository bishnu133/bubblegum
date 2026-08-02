"""M-E: hierarchy compaction for mobile grounding.

Two layers:
  * the pure ``compact_hierarchy_xml`` (prunes non-groundable/invisible subtrees,
    keeps every candidate-producing node), and
  * candidate parity through ``AppiumHierarchyResolver`` — the same targets
    resolve with compaction on and off, and a target buried in a huge decorative
    tree still resolves.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.mobile.hierarchy_compaction import compact_hierarchy_xml
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# ----------------------------------------------------------------------
# compact_hierarchy_xml
# ----------------------------------------------------------------------

def _node_count(xml: str) -> int:
    return sum(1 for _ in ET.fromstring(xml).iter())


def test_drops_decorative_textless_subtrees():
    xml = (
        "<hierarchy>"
        "  <node class='android.widget.FrameLayout'>"
        "    <node class='android.widget.LinearLayout'>"
        "      <node class='android.view.View'/>"
        "      <node class='android.view.View'/>"
        "    </node>"
        "    <node class='android.widget.TextView' text='Login'/>"
        "  </node>"
        "</hierarchy>"
    )
    compacted, stats = compact_hierarchy_xml(xml)
    assert stats["compacted"] is True
    assert stats["dropped_nodes"] >= 2
    # The groundable TextView survives; decorative Views are gone.
    assert "Login" in compacted
    assert "android.view.View" not in compacted


def test_keeps_groundable_and_ancestors():
    xml = (
        "<hierarchy>"
        "  <node class='c1'>"
        "    <node class='c2'>"
        "      <node class='android.widget.TextView' text='Deep target'/>"
        "    </node>"
        "  </node>"
        "</hierarchy>"
    )
    compacted, stats = compact_hierarchy_xml(xml)
    # Ancestors of a kept node are retained so the subtree stays connected.
    assert "Deep target" in compacted
    assert "c1" in compacted and "c2" in compacted


def test_keeps_interactive_textless_node():
    xml = (
        "<hierarchy>"
        "  <node class='android.widget.ImageButton' clickable='true'/>"
        "  <node class='android.view.View'/>"
        "</hierarchy>"
    )
    compacted, _ = compact_hierarchy_xml(xml)
    assert "ImageButton" in compacted
    assert "android.view.View" not in compacted


def test_drops_invisible_textless_but_keeps_invisible_with_text():
    xml = (
        "<hierarchy>"
        "  <node class='android.widget.TextView' text='Shown'/>"
        "  <node class='android.widget.TextView' text='Offscreen' visible-to-user='false'/>"
        "  <node class='android.widget.ProgressBar' visible-to-user='false'/>"
        "</hierarchy>"
    )
    compacted, _ = compact_hierarchy_xml(xml)
    assert "Shown" in compacted
    assert "Offscreen" in compacted           # invisible but has text -> kept
    assert "ProgressBar" not in compacted     # invisible + textless -> dropped


def test_no_change_returns_original_and_flags_not_compacted():
    xml = "<hierarchy><node class='android.widget.TextView' text='Only'/></hierarchy>"
    compacted, stats = compact_hierarchy_xml(xml)
    assert stats["compacted"] is False
    assert compacted == xml


def test_empty_and_unparseable_inputs_are_safe():
    assert compact_hierarchy_xml("")[0] == ""
    out, stats = compact_hierarchy_xml("<hierarchy><broken>")
    assert stats.get("parse_error") is True
    assert out == "<hierarchy><broken>"


def test_large_hierarchy_is_substantially_reduced():
    decorative = "".join("<node class='android.view.View'/>" for _ in range(500))
    xml = f"<hierarchy>{decorative}<node class='android.widget.TextView' text='Submit'/></hierarchy>"
    compacted, stats = compact_hierarchy_xml(xml)
    assert stats["original_nodes"] == 502
    assert stats["kept_nodes"] == 2           # root + the one groundable node
    assert "Submit" in compacted


# ----------------------------------------------------------------------
# Candidate parity through the resolver
# ----------------------------------------------------------------------

_BURIED_XML = (
    "<hierarchy>"
    + "".join(f"<node class='android.view.View' index='{i}'/>" for i in range(300))
    + "<node class='android.widget.Button' text='Continue'/>"
    + "</hierarchy>"
)


def _resolve(xml: str, *, compaction: bool):
    r = AppiumHierarchyResolver()
    intent = StepIntent(
        instruction="Tap Continue",
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase="Continue",
        context={
            "hierarchy_xml": xml,
            "config_mobile_hierarchy_compaction": compaction,
            "config_mobile_hierarchy_max_nodes": 1500,
        },
        options=ExecutionOptions(),
    )
    return r.resolve(intent)


def test_resolver_candidate_parity_with_and_without_compaction():
    off = _resolve(_BURIED_XML, compaction=False)
    on = _resolve(_BURIED_XML, compaction=True)
    assert [c.ref for c in off] == [c.ref for c in on]
    assert on and any("Continue" in c.ref for c in on)


def test_resolver_finds_target_buried_in_decorative_tree():
    on = _resolve(_BURIED_XML, compaction=True)
    assert on
    top = max(on, key=lambda c: c.confidence)
    assert "Continue" in top.ref
