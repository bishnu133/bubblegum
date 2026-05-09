from bubblegum.core.grounding.hydrator import VisualRefHydrator
from bubblegum.core.schemas import ResolvedTarget, StepIntent


def _intent(channel: str = "web") -> StepIntent:
    return StepIntent(instruction="Click Login", channel=channel, platform="web" if channel == "web" else "android", action_type="click")


def test_ocr_visual_ref_with_matched_text_hydrates_to_text_ref_web():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"matched_text": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target is not None
    assert out.target.ref == 'text="Login"'
    assert out.target.metadata["hydrated_from_ref"] == "ocr://block/0"
    assert out.target.metadata["hydration_strategy"] == "text"


def test_ocr_visual_ref_with_no_text_stays_not_hydrated():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"bbox": [1, 2, 3, 4]})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "not_hydrated"
    assert out.reason == "unsupported_visual_ref_hydration"


def test_vision_visual_ref_with_role_and_label_hydrates_to_role_ref_web():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={"role": "button", "label": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target is not None
    assert out.target.ref == 'role=button[name="Login"]'
    assert out.target.metadata["hydration_strategy"] == "role_text"


def test_vision_visual_ref_label_only_hydrates_to_text_ref_web():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={"label": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target is not None
    assert out.target.ref == 'text="Login"'
    assert out.target.metadata["hydration_strategy"] == "text"


def test_visual_ref_on_mobile_remains_not_hydrated():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={"label": "Login"})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("mobile"))
    assert out.status == "not_hydrated"
    assert out.reason == "mobile_visual_hydration_not_supported"


def test_hydration_metadata_and_diagnostics_are_sanitized():
    target = ResolvedTarget(
        ref="ocr://block/0",
        confidence=0.8,
        resolver_name="ocr",
        metadata={"matched_text": "Login", "screenshot_bytes": b"png", "base64": "abc", "raw_payload": "secret"},
    )
    out = VisualRefHydrator().hydrate(target=target, intent=_intent("web"))
    assert out.status == "hydrated"
    assert out.target is not None
    assert "screenshot_bytes" not in out.target.metadata
    assert "base64" not in out.target.metadata
    assert "raw_payload" not in out.target.metadata
    assert b"png" not in out.diagnostics.values()
