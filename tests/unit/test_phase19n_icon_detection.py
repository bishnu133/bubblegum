from bubblegum.core.elements.normalized import NormalizedBounds, NormalizedElement
from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver
from bubblegum.core.mobile.icon_detection import detect_icon_like_mobile_elements, resolve_icon_target_hint
from bubblegum.core.schemas import StepIntent


def _el(ref: str, *, text: str = "", content_desc: str = "", resource_id: str = "", widget_type: str = "android.widget.ImageView", parent: str | None = None):
    return NormalizedElement(id=ref, channel="mobile", platform="android", source_kind="appium_hierarchy", source_ref=ref, text=text, content_desc=content_desc, resource_id=resource_id, widget_type=widget_type, parent_id=parent, bounds=NormalizedBounds())


class _C:
    def __init__(self, ref: str):
        self.ref = ref


def test_detect_icon_with_content_desc_search():
    out = detect_icon_like_mobile_elements(elements=[_el("//s", content_desc="Search")], platform="android")
    assert out["status"] == "resolved"
    assert out["candidate_count"] == 1


def test_detect_icon_with_resource_id_search():
    out = detect_icon_like_mobile_elements(elements=[_el("//s", resource_id="com.example:id/ic_search")], platform="android")
    assert out["status"] == "resolved"


def test_detect_image_button_no_text_weak_icon_candidate():
    out = detect_icon_like_mobile_elements(elements=[_el("//i", widget_type="android.widget.ImageButton")], platform="android")
    assert out["status"] == "resolved"


def test_resolve_tap_search_icon_single():
    elements = [_el("//s", content_desc="Search")]
    out = resolve_icon_target_hint(instruction="tap search icon", candidates=[_C("//s")], elements=elements)
    assert out["status"] == "resolved"
    assert out["selected_candidate_ref"] == "//s"


def test_resolve_delete_icon_in_john_row_via_repeated_region():
    elements = [_el("//d1", content_desc="Delete"), _el("//d2", content_desc="Delete")]
    out = resolve_icon_target_hint(
        instruction="tap delete icon in John row",
        candidates=[_C("//d1"), _C("//d2")],
        elements=elements,
        repeated_region_diagnostics={"status": "resolved", "selected_candidate_ref": "//d2"},
    )
    assert out["status"] == "resolved"
    assert out["icon_hint_type"] == "repeated_region"


def test_resolve_ambiguous_multiple_search_icons_safe():
    elements = [_el("//s1", content_desc="Search"), _el("//s2", content_desc="Search")]
    out = resolve_icon_target_hint(instruction="tap search icon", candidates=[_C("//s1"), _C("//s2")], elements=elements)
    assert out["status"] == "ambiguous"


def test_no_icon_candidate():
    out = resolve_icon_target_hint(instruction="tap search icon", candidates=[_C("//a")], elements=[_el("//a", text="Title", widget_type="android.widget.TextView")])
    assert out["status"] == "no_icon_candidate"


def test_appium_resolver_single_match_unchanged_with_icon_metadata():
    xml = '<hierarchy><node class="android.widget.ImageView" content-desc="Search" bounds="[0,0][10,10]"/></hierarchy>'
    intent = StepIntent(action_type="tap", instruction="tap search icon", channel="mobile", platform="android", context={"hierarchy_xml": xml})
    out = AppiumHierarchyResolver().resolve(intent)
    assert len(out) == 1
    assert out[0].metadata["icon_detection"]["safe_metadata_only"] is True
