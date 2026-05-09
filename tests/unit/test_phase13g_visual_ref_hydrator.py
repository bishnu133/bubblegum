from bubblegum.core.grounding.hydrator import VisualRefHydrator, is_visual_ref
from bubblegum.core.schemas import ResolvedTarget, StepIntent


def _intent() -> StepIntent:
    return StepIntent(instruction="Click Login", channel="web", platform="web", action_type="click")


def test_is_visual_ref_true_for_ocr_scheme():
    assert is_visual_ref("ocr://block/0") is True


def test_is_visual_ref_true_for_vision_scheme():
    assert is_visual_ref("vision://target/0") is True


def test_is_visual_ref_false_for_non_visual_refs():
    assert is_visual_ref('text="Login"') is False
    assert is_visual_ref('role=button[name="Login"]') is False
    assert is_visual_ref("#login") is False
    assert is_visual_ref("//android.widget.Button[@text='Login']") is False


def test_non_visual_target_returns_noop_and_unmutated_target():
    target = ResolvedTarget(ref='text="Login"', confidence=0.9, resolver_name="exact_text", metadata={"safe": True})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent())

    assert out.status == "not_hydrated"
    assert out.reason == "not_visual_ref"
    assert out.target == target
    assert out.original_ref == target.ref
    assert out.hydrated_ref == target.ref


def test_visual_target_returns_failsafe_not_hydrated_with_stable_reason():
    target = ResolvedTarget(ref="ocr://block/0", confidence=0.8, resolver_name="ocr", metadata={"bbox": [1, 2, 3, 4]})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent())

    assert out.status == "not_hydrated"
    assert out.reason == "unsupported_visual_ref_hydration"
    assert out.target is None
    assert out.original_ref == "ocr://block/0"
    assert out.hydrated_ref is None


def test_hydrator_diagnostics_never_include_raw_screenshot_bytes():
    target = ResolvedTarget(ref="vision://target/0", confidence=0.8, resolver_name="vision_model", metadata={"bbox": [1, 2, 3, 4]})
    out = VisualRefHydrator().hydrate(target=target, intent=_intent())

    assert isinstance(out.diagnostics, dict)
    assert "screenshot" not in out.diagnostics
    assert b"png" not in out.diagnostics.values()
