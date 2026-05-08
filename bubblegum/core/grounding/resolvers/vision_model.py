"""
bubblegum/core/grounding/resolvers/vision_model.py
VisionModelResolver injected-candidate MVP (Phase 11D).

Consumes normalized/injected vision candidates from intent.context["vision_candidates"]
without provider/model calls or screenshot pipeline execution.
"""

from __future__ import annotations

import re

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.grounding.signals import make_signals
from bubblegum.core.schemas import ResolvedTarget, StepIntent
from bubblegum.core.vision import normalize_vision_candidates


class VisionModelResolver(Resolver):

    name = "vision_model"
    priority = 70
    channels = ["web", "mobile"]
    cost_level = "high"
    tier = 3

    def supports(self, intent: StepIntent) -> bool:
        """Run only when vision is enabled and screenshot sharing is allowed."""
        return bool(intent.context.get("config_vision_enabled", True))

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """Resolve from injected normalized vision candidates only (no provider calls)."""
        if not bool(intent.context.get("config_vision_enabled", True)):
            return []

        normalized = normalize_vision_candidates(intent.context.get("vision_candidates"))
        if not normalized:
            return []

        instruction_tokens = _tokens(intent.instruction)
        label_counts = _label_counts(normalized)

        out: list[ResolvedTarget] = []
        for idx, candidate in enumerate(normalized):
            matched_text = (candidate.text or candidate.label or "").strip()
            text_signal = _text_match_signal(intent.instruction, candidate.text, candidate.label)
            role_signal = _role_match_signal(intent.instruction, candidate.role)
            visibility = _clamp(candidate.confidence)
            uniqueness = 1.0 / label_counts[_norm_key(candidate.text or candidate.label)]
            proximity = 0.5
            memory_history = 0.0

            signals = make_signals(
                text_match=text_signal,
                role_match=role_signal,
                visibility=visibility,
                uniqueness=uniqueness,
                proximity=proximity,
                memory_history=memory_history,
            )

            weighted = (
                signals["text_match"] * 0.30
                + signals["role_match"] * 0.20
                + signals["visibility"] * 0.15
                + signals["uniqueness"] * 0.15
                + signals["proximity"] * 0.10
                + signals["memory_history"] * 0.10
            )
            confidence = _clamp(weighted)

            if confidence < 0.48:
                continue
            if instruction_tokens and not _has_any_token_overlap(instruction_tokens, matched_text, candidate.label, candidate.role):
                continue

            metadata = {
                "source": "vision",
                "matched_text": matched_text,
                "label": candidate.label,
                "role": candidate.role,
                "bbox": candidate.bbox,
                "vision_confidence": visibility,
                "candidate_index": idx,
                "signals": signals,
            }
            out.append(
                ResolvedTarget(
                    ref=f"vision://target/{idx}",
                    confidence=confidence,
                    resolver_name=self.name,
                    metadata=metadata,
                )
            )
        return out


def _norm_key(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _tokens(value: str | None) -> set[str]:
    text = _norm_key(value)
    return {t for t in re.split(r"[^a-z0-9]+", text) if t}


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else float(value)


def _label_counts(candidates) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in candidates:
        key = _norm_key(c.text or c.label)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _has_any_token_overlap(instruction_tokens: set[str], *texts: str | None) -> bool:
    candidate_tokens: set[str] = set()
    for text in texts:
        candidate_tokens |= _tokens(text)
    return bool(instruction_tokens & candidate_tokens)


def _text_match_signal(instruction: str, text: str | None, label: str | None) -> float:
    inst = _norm_key(instruction)
    inst_tokens = _tokens(instruction)
    candidate_text = _norm_key(text or label)
    candidate_tokens = _tokens(candidate_text)

    if not candidate_text or not inst_tokens:
        return 0.0
    if candidate_text in inst or inst in candidate_text:
        return 1.0

    overlap = len(inst_tokens & candidate_tokens)
    if overlap == 0:
        return 0.0
    return min(0.9, overlap / max(1, len(candidate_tokens)))


def _role_match_signal(instruction: str, role: str | None) -> float:
    if not role:
        return 0.0
    inst = _norm_key(instruction)
    role_n = _norm_key(role)
    if role_n in {"button", "link"} and any(k in inst for k in ("click", "tap", "press")):
        return 1.0
    if role_n in {"input", "textbox", "field"} and any(k in inst for k in ("type", "enter", "input")):
        return 1.0
    if role_n in inst:
        return 0.7
    return 0.0
