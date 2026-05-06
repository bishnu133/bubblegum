from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.grounding.resolvers.ocr import OCRResolver
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


def _block(text: str, bbox=None, confidence: float = 0.9):
    return {
        "text": text,
        "bbox": bbox or [10, 10, 100, 40],
        "confidence": confidence,
    }


def test_returns_empty_without_ocr_blocks():
    resolver = OCRResolver()
    assert resolver.resolve(_intent("Click Sign In")) == []


def test_respects_config_ocr_enabled_false():
    resolver = OCRResolver()
    intent = _intent("Click Sign In", context={"config_ocr_enabled": False, "ocr_blocks": [_block("Sign In")]})
    assert resolver.resolve(intent) == []


def test_returns_candidate_for_exact_ocr_text_match_and_ref_format():
    resolver = OCRResolver()
    intent = _intent("Click Sign In", context={"ocr_blocks": [_block("Sign In")]})
    results = resolver.resolve(intent)
    assert len(results) == 1
    assert results[0].ref == "ocr://block/0"
    assert results[0].resolver_name == "ocr"


def test_emits_expected_metadata_fields():
    resolver = OCRResolver()
    block = _block("Order Confirmed", bbox=[1, 2, 3, 4], confidence=0.77)
    intent = _intent("Verify text Order Confirmed visible", context={"ocr_blocks": [block]})
    results = resolver.resolve(intent)
    assert len(results) == 1
    md = results[0].metadata
    assert md["source"] == "ocr"
    assert md["matched_text"] == "Order Confirmed"
    assert md["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert md["ocr_confidence"] == 0.77
    assert md["block_index"] == 0
    assert isinstance(md["signals"], dict)


def test_supports_web_and_mobile_channels():
    resolver = OCRResolver()
    web = _intent("Click Submit", channel="web", context={"ocr_blocks": [_block("Submit")]})
    mobile = _intent("Tap Submit", channel="mobile", context={"ocr_blocks": [_block("Submit")]})
    assert resolver.can_run(web) is True
    assert resolver.can_run(mobile) is True
    assert resolver.resolve(web)
    assert resolver.resolve(mobile)


def test_duplicate_text_reduces_uniqueness_deterministically():
    resolver = OCRResolver()
    intent = _intent(
        "Click Continue",
        context={"ocr_blocks": [_block("Continue"), _block("Continue", bbox=[20, 20, 110, 50], confidence=0.85)]},
    )
    results = resolver.resolve(intent)
    assert len(results) == 2
    assert results[0].metadata["signals"]["uniqueness"] == 0.5
    assert results[1].metadata["signals"]["uniqueness"] == 0.5


def test_weak_unrelated_text_returns_empty():
    resolver = OCRResolver()
    intent = _intent("Click Login", context={"ocr_blocks": [_block("Shipping Address"), _block("Account Settings")]})
    assert resolver.resolve(intent) == []


def test_ranker_can_score_ocr_candidate_using_signals():
    resolver = OCRResolver()
    intent = _intent("Click Sign In", context={"ocr_blocks": [_block("Sign In", confidence=0.95)]})
    candidate = resolver.resolve(intent)[0]
    score = CandidateRanker().score(candidate)
    assert score >= 0.66
