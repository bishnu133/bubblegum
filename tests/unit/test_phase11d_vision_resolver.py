from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.grounding.resolvers.vision_model import VisionModelResolver
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def _intent(instruction: str, *, channel: str = "web", context: dict | None = None) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel=channel,
        platform="web" if channel == "web" else "android",
        action_type="click",
        context=context or {},
        options=ExecutionOptions(max_cost_level="high"),
    )


def _cand(label: str, *, text: str | None = None, role: str | None = "button", bbox=None, confidence: float = 0.9):
    return {
        "label": label,
        "text": text,
        "role": role,
        "bbox": bbox or [10, 10, 100, 40],
        "confidence": confidence,
    }


def test_returns_empty_when_vision_candidates_missing():
    assert VisionModelResolver().resolve(_intent("Click Login")) == []


def test_returns_empty_when_vision_candidates_empty():
    assert VisionModelResolver().resolve(_intent("Click Login", context={"vision_candidates": []})) == []


def test_respects_config_vision_enabled_false():
    intent = _intent("Click Login", context={"config_vision_enabled": False, "vision_candidates": [_cand("Login")]})
    assert VisionModelResolver().resolve(intent) == []


def test_returns_candidate_for_exact_label_text_match_and_ref_format():
    intent = _intent("Click Sign In", context={"vision_candidates": [_cand("Sign In", text="Sign In")]})
    out = VisionModelResolver().resolve(intent)
    assert len(out) == 1
    assert out[0].ref == "vision://target/0"
    assert out[0].resolver_name == "vision_model"


def test_metadata_contains_expected_fields():
    intent = _intent("Click Checkout", context={"vision_candidates": [_cand("Checkout", bbox=[1, 2, 3, 4], confidence=0.77)]})
    out = VisionModelResolver().resolve(intent)
    md = out[0].metadata
    assert md["source"] == "vision"
    assert md["matched_text"] == "Checkout"
    assert md["label"] == "Checkout"
    assert md["role"] == "button"
    assert md["bbox"] == [1, 2, 3, 4]
    assert md["vision_confidence"] == 0.77
    assert md["candidate_index"] == 0
    assert isinstance(md["signals"], dict)


def test_supports_web_and_mobile_channels():
    resolver = VisionModelResolver()
    web = _intent("Click Submit", channel="web", context={"vision_candidates": [_cand("Submit")]})
    mobile = _intent("Tap Submit", channel="mobile", context={"vision_candidates": [_cand("Submit")]})
    assert resolver.can_run(web) is True
    assert resolver.can_run(mobile) is True
    assert resolver.resolve(web)
    assert resolver.resolve(mobile)


def test_duplicate_text_reduces_uniqueness_deterministically():
    intent = _intent(
        "Click Continue",
        context={"vision_candidates": [_cand("Continue"), _cand("Continue", bbox=[20, 20, 120, 50], confidence=0.85)]},
    )
    out = VisionModelResolver().resolve(intent)
    assert len(out) == 2
    assert out[0].metadata["signals"]["uniqueness"] == 0.5
    assert out[1].metadata["signals"]["uniqueness"] == 0.5


def test_unrelated_weak_candidate_returns_empty():
    intent = _intent("Click Login", context={"vision_candidates": [_cand("Shipping Address"), _cand("Account Settings")]})
    assert VisionModelResolver().resolve(intent) == []


def test_ranker_can_score_candidate_using_emitted_signals():
    intent = _intent("Click Sign In", context={"vision_candidates": [_cand("Sign In", confidence=0.95)]})
    candidate = VisionModelResolver().resolve(intent)[0]
    score = CandidateRanker().score(candidate)
    assert score >= 0.60


def test_resolver_metadata_unchanged():
    resolver = VisionModelResolver()
    assert resolver.name == "vision_model"
    assert resolver.priority == 70
    assert resolver.tier == 3
    assert resolver.cost_level == "high"
    assert resolver.channels == ["web", "mobile"]
    assert resolver.required_context() == []
