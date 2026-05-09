import json

from bubblegum.core.grounding.hydrator import VisualRefHydrator
from bubblegum.core.schemas import ResolvedTarget, StepIntent


_HIERARCHY = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy>
  <android.widget.FrameLayout>
    <android.widget.Button text='Login'/>
    <android.widget.ImageView content-desc='Settings'/>
    <android.widget.TextView resource-id='com.example:id/title'/>
  </android.widget.FrameLayout>
</hierarchy>"""


def _intent(hierarchy_xml: str | None) -> StepIntent:
    context = {}
    if hierarchy_xml is not None:
        context["hierarchy_xml"] = hierarchy_xml
    return StepIntent(
        instruction="Tap target",
        channel="mobile",
        platform="android",
        action_type="tap",
        context=context,
    )


def test_ocr_mobile_hydrates_using_text():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "hydrated"
    assert out.target is not None
    ref_obj = json.loads(out.target.ref)
    assert ref_obj["by"] == "xpath"
    assert "@text='Login'" in ref_obj["value"]
    assert out.target.metadata["hydration_strategy"] == "mobile_text"


def test_vision_mobile_hydrates_using_content_desc():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={"label": "Settings"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "hydrated"
    assert out.target is not None
    assert out.target.metadata["hydration_strategy"] == "mobile_content_desc"
    assert "@content-desc='Settings'" in json.loads(out.target.ref)["value"]


def test_mobile_hydrates_using_resource_id_when_text_and_content_desc_missing():
    target = ResolvedTarget(
        ref="vision://target/0",
        confidence=0.8,
        resolver_name="vision_model",
        metadata={"matched_text": "com.example:id/title"},
    )
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "hydrated"
    assert out.target is not None
    assert out.target.metadata["hydration_strategy"] == "mobile_resource_id"
    assert "@resource-id='com.example:id/title'" in json.loads(out.target.ref)["value"]


def test_mobile_missing_hierarchy_fails_with_stable_reason():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(None))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_no_hierarchy"


def test_mobile_missing_metadata_fails_with_stable_reason():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_unsupported_metadata"


def test_mobile_no_match_fails_with_stable_reason():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "NotFound"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_no_match"


def test_mobile_ambiguous_match_fails_with_stable_reason():
    xml = """<hierarchy><node text='Login'/><node text='Login'/></hierarchy>"""
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(xml))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_ambiguous_match"


def test_mobile_invalid_xml_fails_with_stable_reason():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("<hierarchy><node>"))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_invalid_hierarchy"


def test_mobile_hydrated_ref_is_json_xpath_for_adapter():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    ref_obj = json.loads(out.target.ref)
    assert set(ref_obj.keys()) == {"by", "value"}
    assert ref_obj["by"] == "xpath"
    assert ref_obj["value"].startswith("//")


def test_mobile_unsafe_metadata_sanitized():
    target = ResolvedTarget(
        ref="ocr://block/0",
        confidence=0.8,
        resolver_name="ocr",
        metadata={"matched_text": "Login", "screenshot_bytes": b"png", "base64": "abc", "raw_payload": "secret"},
    )
    out = VisualRefHydrator().hydrate(target=target, intent=_intent(_HIERARCHY))
    assert out.status == "hydrated"
    assert out.target is not None
    assert "screenshot_bytes" not in out.target.metadata
    assert "base64" not in out.target.metadata
    assert "raw_payload" not in out.target.metadata
