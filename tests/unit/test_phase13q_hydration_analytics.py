from __future__ import annotations

from bubblegum.core.schemas import ResolvedTarget, StepResult
from bubblegum.reporting.html_report import build_report_analytics


def _result_with_meta(status: str, meta: dict) -> StepResult:
    return StepResult(
        status=status,
        action="Click",
        confidence=0.9,
        target=ResolvedTarget(ref='text="Login"', confidence=0.9, resolver_name="ocr", metadata=meta),
    )


def test_hydration_summary_counts_and_groupings():
    results = [
        _result_with_meta(
            "passed",
            {
                "hydration_status": "hydrated",
                "hydration_source": "ocr",
                "hydration_strategy": "text",
                "hydration_channel": "web",
                "hydration_reason": "hydrated_text_ref",
            },
        ),
        _result_with_meta(
            "failed",
            {
                "hydration_status": "not_hydrated",
                "hydration_source": "vision",
                "hydration_strategy": "role_name",
                "hydration_channel": "mobile",
                "hydration_reason": "mobile_visual_hydration_no_match",
            },
        ),
        _result_with_meta(
            "failed",
            {
                "hydration_status": "blocked",
                "hydration_source": "vision",
                "hydration_strategy": "text",
                "hydration_channel": "web",
                "hydration_reason": "policy_blocked",
            },
        ),
        StepResult(status="skipped", action="Noop", confidence=0.0),
    ]

    analytics = build_report_analytics(results)
    hs = analytics["hydration_summary"]

    assert hs["total_events"] == 3
    assert hs["status_counts"] == {"hydrated": 1, "not_hydrated": 1, "blocked": 1}
    assert hs["by_source"] == {"ocr": 1, "vision": 2}
    assert hs["by_strategy"] == {"text": 2, "role_name": 1}
    assert hs["by_channel"] == {"web": 2, "mobile": 1}
    assert hs["by_reason"] == {
        "hydrated_text_ref": 1,
        "mobile_visual_hydration_no_match": 1,
        "policy_blocked": 1,
    }


def test_hydration_summary_empty_when_no_hydration_metadata():
    analytics = build_report_analytics([StepResult(status="passed", action="Click", confidence=1.0)])
    hs = analytics["hydration_summary"]

    assert hs["total_events"] == 0
    assert hs["status_counts"] == {"hydrated": 0, "not_hydrated": 0, "blocked": 0}
    assert hs["by_source"] == {}
    assert hs["by_strategy"] == {}
    assert hs["by_channel"] == {}
    assert hs["by_reason"] == {}


def test_unsafe_keys_do_not_influence_hydration_summary():
    analytics = build_report_analytics(
        [
            _result_with_meta(
                "passed",
                {
                    "hydration_status": "hydrated",
                    "hydration_reason": "hydrated_text_ref",
                    "hierarchy_xml": "<root/>",
                    "screenshot_bytes": "abc",
                    "base64": "zzz",
                    "raw_payload": "token",
                    "provider_response": "body",
                    "secret": "key",
                    "candidate_dump": ["x"],
                    "hydration_original_ref": "ocr://block/0",
                    "hydration_hydrated_ref": 'text="Login"',
                },
            )
        ]
    )

    hs = analytics["hydration_summary"]
    assert hs["total_events"] == 1
    assert hs["status_counts"]["hydrated"] == 1
    assert hs["by_reason"] == {"hydrated_text_ref": 1}


def test_existing_analytics_keys_unchanged_plus_hydration_summary():
    analytics = build_report_analytics([StepResult(status="failed", action="Click", confidence=0.2)])
    assert "total" in analytics
    assert "status_counts" in analytics
    assert "resolver_win_counts" in analytics
    assert "confidence_summary" in analytics
    assert "error_type_counts" in analytics
    assert "hydration_summary" in analytics
