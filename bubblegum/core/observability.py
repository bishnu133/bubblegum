"""
bubblegum/core/observability.py
===============================
Streaming observability for grounding decisions (Task #8).

Bubblegum already renders end-of-run reports (Allure / JSON / JUnit / HTML) and
a human-readable ``explain``. This module adds the *streaming* half enterprises
need: every step emits a structured, machine-readable observation — which
resolvers ran, the ranked candidates, the winner + confidence + tier, timing,
running cost, and outcome — to a pluggable sink as it happens, so it can flow
into a dashboard / APM / audit log without waiting for the run to finish.

Sinks are pluggable and dormant by default (NullSink):
  * JSONLFileSink  — append one JSON line per step (diffable, greppable, cheap).
  * OTelSink       — one OpenTelemetry span per step *if* opentelemetry is
                     installed; a graceful no-op otherwise (no hard dependency).
  * CallableSink   — hand each observation to your own function.
  * MultiSink      — fan out to several sinks.

Everything is fail-safe: emitting an observation must never break a test run.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from bubblegum.core.grounding.ranker import _WEIGHTS, compute_confidence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sink protocol + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class ObservabilitySink(Protocol):
    def emit(self, observation: dict) -> None: ...


class NullSink:
    """Default sink — discards everything (observability off)."""

    def emit(self, observation: dict) -> None:  # noqa: D401
        return None


class CallableSink:
    """Forward each observation to a user callable."""

    def __init__(self, fn) -> None:
        if not callable(fn):
            raise TypeError("CallableSink requires a callable(observation: dict).")
        self._fn = fn

    def emit(self, observation: dict) -> None:
        try:
            self._fn(observation)
        except Exception as exc:  # noqa: BLE001 — observability must never break a run
            logger.debug("CallableSink.emit failed: %s", exc)


class JSONLFileSink:
    """Append one JSON object per line to a file (thread + process safe-ish)."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("JSONLFileSink: could not create dir for %s: %s", self._path, exc)

    def emit(self, observation: dict) -> None:
        try:
            line = json.dumps(observation, default=str)
            with self._lock:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.debug("JSONLFileSink.emit failed: %s", exc)


class OTelSink:
    """Emit one OpenTelemetry span per step, if opentelemetry is available.

    No hard dependency: when the SDK is not installed the sink is a silent no-op,
    so the same config works in environments with and without OTel.
    """

    def __init__(self, service_name: str = "bubblegum") -> None:
        self._tracer = None
        try:
            from opentelemetry import trace  # type: ignore[import]
            self._tracer = trace.get_tracer(service_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OTelSink: opentelemetry unavailable, sink is inert: %s", exc)

    def emit(self, observation: dict) -> None:
        if self._tracer is None:
            return
        try:
            name = observation.get("action") or "bubblegum.step"
            with self._tracer.start_as_current_span(name) as span:
                for key, value in _otel_attributes(observation).items():
                    span.set_attribute(key, value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OTelSink.emit failed: %s", exc)


class MultiSink:
    """Fan out each observation to several sinks."""

    def __init__(self, *sinks: ObservabilitySink) -> None:
        self._sinks = [s for s in sinks if s is not None]

    def emit(self, observation: dict) -> None:
        for sink in self._sinks:
            try:
                sink.emit(observation)
            except Exception as exc:  # noqa: BLE001
                logger.debug("MultiSink child emit failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-global sink + run/step correlation
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_sink: ObservabilitySink = NullSink()
_run_id: str = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
_step_seq: int = 0


def configure_observability(sink: ObservabilitySink | None) -> None:
    """Install the active sink (None restores the NullSink)."""
    global _sink
    _sink = sink or NullSink()


def get_sink() -> ObservabilitySink:
    return _sink


def reset(run_id: str | None = None) -> None:
    """Start a fresh run id / step counter (used at session start and in tests)."""
    global _run_id, _step_seq
    with _lock:
        _step_seq = 0
        if run_id is not None:
            _run_id = run_id


def record(result) -> None:
    """Build and emit an observation for a StepResult. Never raises."""
    try:
        observation = build_observation(result)
        _sink.emit(observation)
    except Exception as exc:  # noqa: BLE001 — observability must never break a run
        logger.debug("observability.record failed: %s", exc)


# ---------------------------------------------------------------------------
# Observation builder — reads only what StepResult already captured
# ---------------------------------------------------------------------------

def build_observation(result, *, max_candidates: int = 5) -> dict:
    """Turn a StepResult into a structured, JSON-serializable observation."""
    global _step_seq
    with _lock:
        _step_seq += 1
        step_index = _step_seq

    # Running cost snapshot (best-effort).
    cost_usd = 0.0
    try:
        from bubblegum.core import cost
        cost_usd = round(cost.spent(), 6)
    except Exception:  # noqa: BLE001
        pass

    winner = None
    target = getattr(result, "target", None)
    if target is not None:
        winner = {
            "ref": target.ref,
            "resolver": target.resolver_name,
            "tier": _tier_of(target.resolver_name),
            "role": (target.metadata or {}).get("role"),
        }

    error = None
    err = getattr(result, "error", None)
    if err is not None:
        error = {"type": getattr(err, "error_type", None), "message": getattr(err, "message", None)}

    winner_ref = winner["ref"] if winner else None
    candidates = _ranked_candidates(result)[:max_candidates]
    cand_out = [
        {"ref": c.ref, "resolver": c.resolver_name, "score": round(_score(c), 4),
         "winner": c.ref == winner_ref}
        for c in candidates
    ]

    resolvers = [
        {
            "name": t.resolver_name,
            "ran": bool(t.can_run),
            "candidates": len(t.candidates),
            "duration_ms": t.duration_ms,
            "reason_skipped": getattr(t, "reason_skipped", None),
        }
        for t in getattr(result, "traces", []) or []
    ]

    return {
        "ts": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
        "run_id": _run_id,
        "step": step_index,
        "action": getattr(result, "action", None),
        "status": getattr(result, "status", None),
        "confidence": round(float(getattr(result, "confidence", 0.0)), 4),
        "duration_ms": getattr(result, "duration_ms", 0),
        "cost_usd": cost_usd,
        "winner": winner,
        "error": error,
        "candidates": cand_out,
        "resolvers": resolvers,
    }


# ---------------------------------------------------------------------------
# Small helpers (mirrors of the explain renderer, kept in core to avoid a
# core -> reporting import inversion)
# ---------------------------------------------------------------------------

def _score(target) -> float:
    signals = target.metadata.get("signals") if isinstance(target.metadata, dict) else None
    if isinstance(signals, dict):
        return compute_confidence(signals)
    return float(target.confidence)


def _ranked_candidates(result) -> list:
    best: dict[str, Any] = {}
    for trace in getattr(result, "traces", []) or []:
        for cand in trace.candidates:
            prev = best.get(cand.ref)
            if prev is None or _score(cand) > _score(prev):
                best[cand.ref] = cand
    return sorted(best.values(), key=_score, reverse=True)


_TIER_CACHE: dict[str, int] | None = None


def _tier_of(resolver_name: str | None) -> int | None:
    global _TIER_CACHE
    if not resolver_name:
        return None
    if _TIER_CACHE is None:
        try:
            from bubblegum.core.grounding.registry import ResolverRegistry
            _TIER_CACHE = {r.name: r.tier for r in ResolverRegistry().all()}
        except Exception:  # noqa: BLE001
            _TIER_CACHE = {}
    return _TIER_CACHE.get(resolver_name)


def _otel_attributes(observation: dict) -> dict:
    """Flatten an observation into primitive OTel span attributes."""
    attrs: dict[str, Any] = {
        "bubblegum.status": str(observation.get("status")),
        "bubblegum.confidence": float(observation.get("confidence", 0.0)),
        "bubblegum.duration_ms": int(observation.get("duration_ms", 0)),
        "bubblegum.cost_usd": float(observation.get("cost_usd", 0.0)),
        "bubblegum.run_id": str(observation.get("run_id")),
        "bubblegum.step": int(observation.get("step", 0)),
        "bubblegum.resolver_count": len(observation.get("resolvers", [])),
    }
    winner = observation.get("winner")
    if winner:
        attrs["bubblegum.winner_ref"] = str(winner.get("ref"))
        attrs["bubblegum.winner_resolver"] = str(winner.get("resolver"))
        if winner.get("tier") is not None:
            attrs["bubblegum.winner_tier"] = int(winner["tier"])
    error = observation.get("error")
    if error and error.get("type"):
        attrs["bubblegum.error_type"] = str(error["type"])
    return attrs


# ---------------------------------------------------------------------------
# Config-driven sink construction
# ---------------------------------------------------------------------------

def build_sink_from_config(config) -> ObservabilitySink:
    """Build the sink described by config.observability. Never raises."""
    obs = getattr(config, "observability", None)
    if obs is None or not getattr(obs, "enabled", False):
        return NullSink()
    export = (getattr(obs, "export", "none") or "none").lower().strip()
    try:
        if export == "jsonl":
            return JSONLFileSink(getattr(obs, "file", ".bubblegum/observability.jsonl"))
        if export == "otel":
            return OTelSink(getattr(obs, "service_name", "bubblegum"))
        if export == "both":
            return MultiSink(
                JSONLFileSink(getattr(obs, "file", ".bubblegum/observability.jsonl")),
                OTelSink(getattr(obs, "service_name", "bubblegum")),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("build_sink_from_config failed (%s); observability off", exc)
    return NullSink()
