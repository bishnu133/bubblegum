"""
tests/unit/test_vision_grounding_backend.py
===========================================
Task #6 — pluggable screenshot-grounding backend, first-class on mobile.

Covers the self-hosted HTTP grounder (OmniParser/UI-TARS/candidate response
shapes), the config-driven factory + SDK auto-wiring (with manual override),
the relaxed privacy/cost gating for in-network grounders, and the guard that a
coordinate ref is never persisted.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.core.config import BubblegumConfig
from bubblegum.core.vision import HTTPGroundingProvider, get_vision_provider
from bubblegum.core.vision.backends.http import HTTPGroundingProvider as HGP


def _transport(payload: dict):
    def _t(url, data, headers, timeout):
        # Sanity: the request carries instruction + base64 image.
        sent = json.loads(data.decode("utf-8"))
        assert "image_base64" in sent and sent["instruction"]
        return json.dumps(payload)
    return _t


# --------------------------------------------------------------------------- #
# HTTP backend response normalization (3 shapes)
# --------------------------------------------------------------------------- #

def test_http_normalizes_native_candidates():
    p = HGP("http://x", transport=_transport({
        "candidates": [{"label": "Save", "role": "button", "bbox": [1, 2, 3, 4], "confidence": 0.9}]
    }))
    out = p.detect_targets(b"PNG", "click Save")
    assert out[0].label == "Save" and out[0].role == "button" and out[0].bbox == [1, 2, 3, 4]


def test_http_normalizes_omniparser_elements():
    p = HGP("http://x", transport=_transport({
        "elements": [
            {"content": "Login", "type": "button", "bbox": [10, 20, 110, 60]},
            {"caption": "", "bbox": [0, 0, 1, 1]},   # empty label -> dropped
        ]
    }))
    out = p.detect_targets(b"PNG", "tap Login")
    assert len(out) == 1
    assert out[0].label == "Login" and out[0].bbox == [10, 20, 110, 60]


def test_http_normalizes_point_response():
    p = HGP("http://x", transport=_transport({"point": [42, 99]}))
    out = p.detect_targets(b"PNG", "tap here")
    assert len(out) == 1
    assert out[0].bbox == [41, 98, 43, 100]


def test_http_failsafe_on_transport_error():
    def boom(url, data, headers, timeout):
        raise RuntimeError("service down")
    p = HGP("http://x", transport=boom)
    assert p.detect_targets(b"PNG", "tap") == []
    assert p.get_last_diagnostic()["code"] == "request_failed"


def test_http_failsafe_on_bad_json():
    p = HGP("http://x", transport=lambda *a: "not json")
    assert p.detect_targets(b"PNG", "tap") == []
    assert p.get_last_diagnostic()["code"] == "parse_failed"


def test_http_requires_endpoint():
    with pytest.raises(ValueError):
        HGP("")


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def _cfg(grounding=None, ai=None, privacy=None):
    return BubblegumConfig.model_validate({
        "grounding": grounding or {},
        "ai": ai or {"enabled": True, "provider": "openai", "model": "gpt-4o-mini"},
        "privacy": privacy or {},
    })


def test_factory_dormant_by_default():
    assert get_vision_provider(_cfg()) is None


def test_factory_builds_http_backend():
    c = _cfg(grounding={"enable_vision": True, "vision_backend": "http",
                        "vision_endpoint": "http://localhost:8000/ground"})
    p = get_vision_provider(c)
    assert isinstance(p, HTTPGroundingProvider)


def test_factory_http_without_endpoint_is_dormant():
    c = _cfg(grounding={"enable_vision": True, "vision_backend": "http"})
    assert get_vision_provider(c) is None


def test_factory_hosted_without_model_is_dormant():
    c = _cfg(grounding={"enable_vision": True, "vision_backend": "openai"})
    assert get_vision_provider(c) is None   # ai.vision_model unset


# --------------------------------------------------------------------------- #
# SDK auto-wiring + manual override + gating
# --------------------------------------------------------------------------- #

def test_sdk_autowires_and_relaxes_gating_for_local(monkeypatch):
    import bubblegum.core.sdk as sdk
    from bubblegum.core.schemas import ExecutionOptions, StepIntent

    cfg = BubblegumConfig.model_validate({
        "grounding": {"enable_vision": True, "vision_backend": "http",
                      "vision_endpoint": "http://localhost:9000/ground"},
        "privacy": {"process_screenshots_for_vision": True, "vision_is_local": True},
    })
    try:
        sdk.configure_runtime(cfg)
        assert isinstance(sdk._vision_provider, HTTPGroundingProvider)
        assert cfg.vision_enabled is True                     # local satisfies privacy
        assert sdk._vision_privacy_ok() is True
        # Local grounder is reachable under the default medium policy (mobile-first).
        intent = StepIntent(instruction="tap Login", channel="mobile", action_type="tap",
                            options=ExecutionOptions(max_cost_level="medium"))
        assert sdk._allows_provider_vision_cost(intent) is True
    finally:
        # Restore the default runtime config for other tests.
        sdk.configure_runtime(BubblegumConfig())


def test_manual_provider_overrides_config_wiring():
    import bubblegum.core.sdk as sdk

    class _Fake:
        def detect_targets(self, image_bytes, instruction, context=None):
            return []
    try:
        sdk.configure_vision_provider(_Fake())
        assert isinstance(sdk._vision_provider, _Fake)
        sdk._wire_vision_provider()                           # must NOT override manual choice
        assert isinstance(sdk._vision_provider, _Fake)
    finally:
        sdk.clear_vision_provider()
        assert sdk._vision_provider_manual is False


# --------------------------------------------------------------------------- #
# Coordinate refs are never cached
# --------------------------------------------------------------------------- #

def test_coordinate_ref_not_cached(tmp_path):
    from bubblegum.core.grounding.resolvers.memory_cache import MemoryCacheResolver
    from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent

    mc = MemoryCacheResolver(db_path=tmp_path / "mem.db")
    intent = StepIntent(
        instruction="tap", channel="mobile", action_type="tap",
        context={"screen_signature": "sig-1"}, options=ExecutionOptions(),
    )
    target = ResolvedTarget(ref="point://100,200", confidence=0.9, resolver_name="vision_model")
    mc.record_success(intent, target)
    # Nothing durable to replay: a point is recomputed each run, never cached.
    assert mc.resolve(intent) == []
