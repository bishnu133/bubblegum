from bubblegum.core.elements.normalized import NormalizedElement, NormalizedBounds
from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.mobile.repeated_structure import detect_repeated_mobile_regions, disambiguate_within_repeated_region
from bubblegum.core.schemas import StepIntent


def _el(id, ref, parent, text="", widget="android.widget.TextView", content_desc=""):
    return NormalizedElement(id=id, channel="mobile", platform="android", source_kind="appium_hierarchy", source_ref=ref, parent_id=parent, widget_type=widget, text=text, content_desc=content_desc, bounds=NormalizedBounds())


def test_detect_repeated_regions_from_synthetic_elements():
    els = [_el("p","p",None, widget="androidx.recyclerview.widget.RecyclerView"), _el("c1","c1","p", text="John"), _el("c2","c2","p", text="Mary")]
    out = detect_repeated_mobile_regions(elements=els)
    assert out["status"] == "resolved"
    assert out["matched_region_count"] == 1
    assert out["safe_metadata_only"] is True


def test_disambiguate_edit_for_john():
    els = [_el("list","list",None, widget="androidx.recyclerview.widget.RecyclerView"), _el("r1","//r1","list", widget="android.view.ViewGroup"), _el("j","//j","r1",text="John"), _el("je","//edit_j","r1",text="Edit", widget="android.widget.Button"), _el("r2","//r2","list", widget="android.view.ViewGroup"), _el("m","//m","r2",text="Mary"), _el("me","//edit_m","r2",text="Edit", widget="android.widget.Button")]
    class C: 
        def __init__(self, ref): self.ref=ref
    out = disambiguate_within_repeated_region(instruction="Tap Edit for John", target_candidates=[C("//edit_j"), C("//edit_m")], anchor_candidates=[], elements=els)
    assert out["status"] == "resolved"
    assert out["selected_candidate_ref"] == "//edit_j"


def test_disambiguate_ambiguous_multiple_anchors():
    els = [_el("list","list",None, widget="androidx.recyclerview.widget.RecyclerView"), _el("r1","//r1","list", widget="android.view.ViewGroup"), _el("a","//a","r1",text="Premium Plan"), _el("r2","//r2","list", widget="android.view.ViewGroup"), _el("b","//b","r2",text="Premium Plan")]
    class C: 
        def __init__(self, ref): self.ref=ref
    out = disambiguate_within_repeated_region(instruction="View details for Premium Plan", target_candidates=[C("//a"), C("//b")], anchor_candidates=[], elements=els)
    assert out["status"] == "ambiguous"


def test_appium_resolver_keeps_single_match_behavior():
    xml = '<hierarchy><node class="android.widget.Button" text="Continue" bounds="[0,0][10,10]"/></hierarchy>'
    intent = StepIntent(action_type="tap", instruction="tap continue", channel="mobile", platform="android", context={"hierarchy_xml": xml})
    out = AppiumHierarchyResolver().resolve(intent)
    assert len(out) == 1
    assert "repeated_region_diagnostics" not in out[0].metadata


def test_appium_resolver_ambiguous_no_anchor_preserved():
    xml = '<hierarchy><node class="android.widget.Button" text="Edit" bounds="[0,0][10,10]"/><node class="android.widget.Button" text="Edit" bounds="[0,20][10,30]"/></hierarchy>'
    intent = StepIntent(action_type="tap", instruction="tap edit", channel="mobile", platform="android", context={"hierarchy_xml": xml})
    out = AppiumHierarchyResolver().resolve(intent)
    assert len(out) == 2
    assert out[0].metadata["repeated_region_diagnostics"]["status"] in {"no_anchor", "no_repeated_region"}


def test_ordinal_second_card():
    els = [_el("list","list",None, widget="androidx.recyclerview.widget.RecyclerView"), _el("r1","//r1","list", widget="android.view.ViewGroup"), _el("one","//one","r1",text="Card A"), _el("r2","//r2","list", widget="android.view.ViewGroup"), _el("two","//two","r2",text="Card B")]
    class C: 
        def __init__(self, ref): self.ref=ref
    out = disambiguate_within_repeated_region(instruction="Tap in second card", target_candidates=[C("//one"), C("//two")], anchor_candidates=[], elements=els)
    assert out["status"] == "resolved"
    assert out["selected_candidate_ref"] == "//two"
