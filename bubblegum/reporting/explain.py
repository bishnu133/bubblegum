"""Human-readable explanation of a Bubblegum grounding decision (A3).

Bubblegum already captures everything needed to explain *why* a step resolved
the way it did: ``StepResult.traces`` holds one ``ResolverTrace`` per resolver
that ran, each candidate carries its per-signal scores in
``metadata["signals"]``, and ``StepResult.target`` is the winner. This module
renders that captured data — it adds no new capture — into a readable report so
debugging a wrong pick does not mean digging through artifact JSON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bubblegum.core.grounding.ranker import _WEIGHTS, compute_confidence

if TYPE_CHECKING:
    from bubblegum.core.schemas import ResolvedTarget, StepResult

# Render signals in the documented confidence-formula order.
_SIGNAL_ORDER = ("text_match", "role_match", "visibility", "uniqueness", "proximity", "memory_history")


def _resolver_tiers() -> dict[str, int]:
    """Map built-in resolver name → tier (best-effort, for the 'stopped at' line)."""
    try:
        from bubblegum.core.grounding.registry import ResolverRegistry

        return {r.name: r.tier for r in ResolverRegistry().all()}
    except Exception:  # pragma: no cover - registry should always build
        return {}


def _candidate_score(target: "ResolvedTarget") -> float:
    """Score a candidate the way the ranker does: weighted signals, else raw confidence."""
    signals = target.metadata.get("signals") if isinstance(target.metadata, dict) else None
    if isinstance(signals, dict):
        return compute_confidence(signals)
    return target.confidence


def _dedupe_candidates(result: "StepResult") -> list["ResolvedTarget"]:
    """Collect candidates across all traces, keeping the highest-scoring per ref."""
    best: dict[str, "ResolvedTarget"] = {}
    for trace in result.traces:
        for cand in trace.candidates:
            existing = best.get(cand.ref)
            if existing is None or _candidate_score(cand) > _candidate_score(existing):
                best[cand.ref] = cand
    return sorted(best.values(), key=_candidate_score, reverse=True)


def _signal_breakdown_lines(target: "ResolvedTarget") -> list[str]:
    signals = target.metadata.get("signals") if isinstance(target.metadata, dict) else None
    if not isinstance(signals, dict):
        return ["       (no signal breakdown — raw resolver confidence)"]
    lines = []
    total = 0.0
    for name in _SIGNAL_ORDER:
        weight = _WEIGHTS.get(name, 0.0)
        value = float(signals.get(name, 0.0))
        contribution = value * weight
        total += contribution
        lines.append(f"       {name:<14} {value:.2f} ×{weight:.2f} = {contribution:.3f}")
    lines.append(f"       {'Σ weighted':<14} {'':>4}        = {min(total, 1.0):.3f}")
    return lines


def format_explanation(result: "StepResult", *, max_candidates: int | None = None) -> str:
    """Return a human-readable explanation of the decision behind a StepResult."""
    lines: list[str] = []
    action = result.action or "(no action)"
    lines.append(f"Bubblegum — explain: {action!r}")

    if result.target is not None:
        winner_ref = result.target.ref
        tiers = _resolver_tiers()
        tier = tiers.get(result.target.resolver_name)
        tier_str = f"Tier {tier}" if tier is not None else "tier ?"
        lines.append(
            f"Decision: {result.status.upper()} → {winner_ref}  "
            f"(resolver={result.target.resolver_name}, confidence={result.confidence:.2f})"
        )
        lines.append(f"Stopped at: {tier_str} ({result.target.resolver_name})")
    else:
        winner_ref = None
        detail = result.error.message if result.error else "no candidate resolved"
        lines.append(f"Decision: {result.status.upper()} → UNRESOLVED ({detail})")

    candidates = _dedupe_candidates(result)
    lines.append("")
    if candidates:
        shown = candidates if max_candidates is None else candidates[:max_candidates]
        lines.append(f"Ranked candidates ({len(candidates)}):")
        for i, cand in enumerate(shown, 1):
            marker = "  ← winner" if cand.ref == winner_ref else ""
            score = _candidate_score(cand)
            lines.append(
                f"  {i}. {cand.ref}   score={score:.2f}   resolver={cand.resolver_name}{marker}"
            )
            lines.extend(_signal_breakdown_lines(cand))
    else:
        lines.append("Ranked candidates (0): none — no resolver returned a candidate.")

    # Why the winner won.
    lines.append("")
    lines.append("Why the winner won:")
    if winner_ref is not None and len(candidates) >= 2:
        top, second = _candidate_score(candidates[0]), _candidate_score(candidates[1])
        gap = top - second
        lines.append(
            f"  Top score {top:.2f} beats runner-up {second:.2f} by {gap:.2f}."
        )
    elif winner_ref is not None:
        lines.append("  Only one candidate cleared the threshold — no contender.")
    else:
        lines.append("  No winner: see the error above.")

    # Resolver run log.
    lines.append("")
    lines.append("Resolvers that ran:")
    if not result.traces:
        lines.append("  (no resolver traces captured)")
    for trace in result.traces:
        if trace.can_run:
            lines.append(
                f"  ✓ {trace.resolver_name:<20} {len(trace.candidates)} candidate(s)   {trace.duration_ms}ms"
            )
        else:
            reason = getattr(trace, "reason_skipped", None) or "not eligible"
            lines.append(f"  · {trace.resolver_name:<20} skipped ({reason})")

    return "\n".join(lines)
