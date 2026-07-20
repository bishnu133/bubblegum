"""
tests/unit/test_observability_and_replay.py
===========================================
Task #8 — streaming observability + replay mode.

Covers the observation builder, the sinks (JSONL / callable / OTel-inert /
multi), config-driven wiring, the @_observed decorator on the entrypoints, and
the replay mode that gates AI providers to dormant for deterministic CI.
"""

from __future__ import annotations

import json

import pytest

from bubblegum.core import observability as obs
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.schemas import ResolvedTarget, ResolverTrace, StepResult, ErrorInfo


def _signals(text=1.0, role=1.0):
    return {"text_match": text, "role_match": role, "visibility": 0.9,
            "uniqueness": 1.0, "proximity": 0.5, "memory_history": 0.0}


def _passed_result():
    win = ResolvedTarget(ref='role=button[name="Go"]', confidence=0.9,
                         resolver_name="fuzzy_text", metadata={"role": "button", "signals": _signals()})
    runner = ResolvedTarget(ref='text="Go away"', confidence=0.6,
                            resolver_name="fuzzy_text", metadata={"role": "link", "signals": _signals(0.6, 0.7)})
    return StepResult(
        status="passed", action="click Go", target=win, confidence=0.9, duration_ms=42,
        traces=[
            ResolverTrace(resolver_name="fuzzy_text", duration_ms=5, candidates=[win, runner], can_run=True),
            ResolverTrace(resolver_name="llm_grounding", duration_ms=0, candidates=[], can_run=False, reason_skipped="cost"),
        ],
    )


# --------------------------------------------------------------------------- #
# Observation builder
# --------------------------------------------------------------------------- #

def test_build_observation_shape():
    o = obs.build_observation(_passed_result())
    assert o["status"] == "passed"
    assert o["action"] == "click Go"
    assert o["winner"]["ref"] == 'role=button[name="Go"]'
    assert o["winner"]["resolver"] == "fuzzy_text"
    assert o["winner"]["tier"] == 2                      # fuzzy_text is Tier 2
    # candidates ranked, winner flagged, ran/skipped both captured
    assert o["candidates"][0]["winner"] is True
    names = {r["name"]: r for r in o["resolvers"]}
    assert names["llm_grounding"]["ran"] is False
    assert names["llm_grounding"]["reason_skipped"] == "cost"
    assert "cost_usd" in o and "run_id" in o and "step" in o


def test_build_observation_unresolved():
    res = StepResult(status="failed", action="click X", target=None, confidence=0.0,
                     error=ErrorInfo(error_type="ResolutionFailedError", message="no match"))
    o = obs.build_observation(res)
    assert o["winner"] is None
    assert o["error"]["type"] == "ResolutionFailedError"


# --------------------------------------------------------------------------- #
# Sinks
# --------------------------------------------------------------------------- #

def test_callable_sink_receives_observation():
    seen = []
    obs.configure_observability(obs.CallableSink(seen.append))
    try:
        obs.record(_passed_result())
        assert len(seen) == 1 and seen[0]["status"] == "passed"
    finally:
        obs.configure_observability(None)


def test_jsonl_sink_writes_lines(tmp_path):
    path = tmp_path / "obs.jsonl"
    obs.configure_observability(obs.JSONLFileSink(path))
    try:
        obs.record(_passed_result())
        obs.record(_passed_result())
    finally:
        obs.configure_observability(None)
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["action"] == "click Go"


def test_sink_failure_never_raises():
    class _Boom:
        def emit(self, o):
            raise RuntimeError("sink down")
    obs.configure_observability(_Boom())
    try:
        obs.record(_passed_result())   # must not raise
    finally:
        obs.configure_observability(None)


def test_otel_sink_inert_without_dependency():
    # opentelemetry is not installed in the test env -> sink is a silent no-op.
    sink = obs.OTelSink()
    sink.emit({"action": "x"})         # must not raise


def test_null_sink_is_default_after_reset():
    obs.configure_observability(None)
    assert isinstance(obs.get_sink(), obs.NullSink)


# --------------------------------------------------------------------------- #
# Config-driven wiring
# --------------------------------------------------------------------------- #

def test_build_sink_from_config_off_by_default():
    assert isinstance(obs.build_sink_from_config(BubblegumConfig()), obs.NullSink)


def test_build_sink_from_config_jsonl(tmp_path):
    cfg = BubblegumConfig.model_validate({
        "observability": {"enabled": True, "export": "jsonl", "file": str(tmp_path / "o.jsonl")}
    })
    assert isinstance(obs.build_sink_from_config(cfg), obs.JSONLFileSink)


# --------------------------------------------------------------------------- #
# @_observed decorator on the entrypoints
# --------------------------------------------------------------------------- #

def test_observed_decorator_emits(monkeypatch):
    import bubblegum.core.sdk as sdk

    seen = []
    obs.configure_observability(obs.CallableSink(seen.append))

    @sdk._observed
    async def fake_entry():
        return _passed_result()

    import asyncio
    try:
        out = asyncio.run(fake_entry())
        assert out.status == "passed"
        assert len(seen) == 1 and seen[0]["action"] == "click Go"
    finally:
        obs.configure_observability(None)


# --------------------------------------------------------------------------- #
# Replay mode
# --------------------------------------------------------------------------- #

def test_replay_mode_gates_ai_providers():
    import bubblegum.core.sdk as sdk

    replay = BubblegumConfig.model_validate({
        "grounding": {"ai_mode": "replay"},
        "ai": {"enabled": True, "provider": "openai", "model": "gpt-4o-mini",
               "embedding_model": "text-embedding-3-small"},
    })
    try:
        sdk.configure_runtime(replay)
        assert sdk._registry.get("llm_grounding").has_provider is False
        assert sdk._registry.get("semantic").has_provider is False
        assert sdk._build_llm_provider() is None
    finally:
        sdk.configure_runtime(BubblegumConfig())


def test_live_mode_builds_provider():
    import bubblegum.core.sdk as sdk

    live = BubblegumConfig.model_validate({
        "grounding": {"ai_mode": "live"},
        "ai": {"enabled": True, "provider": "openai", "model": "gpt-4o-mini"},
    })
    try:
        sdk.configure_runtime(live)
        assert sdk._registry.get("llm_grounding").has_provider is True
    finally:
        sdk.configure_runtime(BubblegumConfig())
