from __future__ import annotations

import re
from collections import Counter

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.grounding.signals import clamp_signal, make_signals
from bubblegum.core.schemas import ResolvedTarget, StepIntent


_STOPWORDS = {
    "click", "tap", "verify", "type", "get", "text", "visible", "select", "read", "fetch",
    "the", "a", "an", "to", "is", "in", "on", "of", "for", "and", "button", "field",
    "input", "screen", "page", "element",
}


class OCRResolver(Resolver):
    name = "ocr"
    priority = 60
    channels = ["web", "mobile"]
    cost_level = "medium"
    tier = 3

    def supports(self, intent: StepIntent) -> bool:
        """Run only when OCR is enabled in the runtime config context."""
        return bool(intent.context.get("config_ocr_enabled", True))

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """Deterministic injected-block OCR MVP (no external OCR engine calls)."""
        if not self.supports(intent):
            return []

        raw_blocks = intent.context.get("ocr_blocks")
        if not isinstance(raw_blocks, list) or not raw_blocks:
            return []

        instruction_norm = _normalize_text(intent.instruction)
        instruction_tokens = _tokens(intent.instruction)
        if not instruction_tokens:
            return []

        normalized_texts: list[str] = []
        parsed_blocks: list[tuple[int, dict, str, set[str]]] = []

        for idx, block in enumerate(raw_blocks):
            parsed = _parse_block(block)
            if parsed is None:
                continue
            text, bbox, ocr_conf = parsed
            norm_text = _normalize_text(text)
            tokens = _tokens(text)
            if not tokens:
                continue
            normalized_texts.append(norm_text)
            parsed_blocks.append((idx, {"text": text, "bbox": bbox, "confidence": ocr_conf}, norm_text, tokens))

        if not parsed_blocks:
            return []

        duplicates = Counter(normalized_texts)
        candidates: list[ResolvedTarget] = []

        for idx, block, norm_text, block_tokens in parsed_blocks:
            text_match = _text_match_score(
                instruction_norm=instruction_norm,
                instruction_tokens=instruction_tokens,
                block_norm=norm_text,
                block_tokens=block_tokens,
            )
            if text_match < 0.30:
                continue

            ocr_confidence = clamp_signal(block["confidence"])
            uniqueness = 1.0 / duplicates[norm_text]

            signals = make_signals(
                text_match=text_match,
                role_match=0.2,
                visibility=ocr_confidence,
                uniqueness=uniqueness,
                proximity=0.5,
                memory=0.0,
                memory_history=0.0,
            )

            base_conf = clamp_signal(text_match * 0.8 + ocr_confidence * 0.2)
            candidates.append(
                ResolvedTarget(
                    ref=f"ocr://block/{idx}",
                    confidence=base_conf,
                    resolver_name=self.name,
                    metadata={
                        "source": "ocr",
                        "matched_text": block["text"],
                        "bbox": block["bbox"],
                        "ocr_confidence": ocr_confidence,
                        "block_index": idx,
                        "signals": signals,
                    },
                )
            )

        return candidates


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def _tokens(text: str) -> set[str]:
    return {tok for tok in _normalize_text(text).split() if tok and tok not in _STOPWORDS}


def _parse_block(block: object) -> tuple[str, list[float], float] | None:
    if not isinstance(block, dict):
        return None

    text = block.get("text")
    bbox = block.get("bbox")
    conf = block.get("confidence")

    if not isinstance(text, str) or not text.strip():
        return None
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        bbox_vals = [float(v) for v in bbox]
        conf_val = float(conf)
    except (TypeError, ValueError):
        return None

    return text.strip(), bbox_vals, conf_val


def _text_match_score(
    *,
    instruction_norm: str,
    instruction_tokens: set[str],
    block_norm: str,
    block_tokens: set[str],
) -> float:
    if not instruction_tokens or not block_tokens:
        return 0.0

    if instruction_norm == block_norm:
        return 1.0

    if block_norm and block_norm in instruction_norm:
        return 0.95
    if instruction_norm and instruction_norm in block_norm:
        return 0.92

    overlap = len(instruction_tokens & block_tokens)
    if overlap == 0:
        return 0.0

    precision = overlap / len(block_tokens)
    recall = overlap / len(instruction_tokens)
    return clamp_signal(0.6 * recall + 0.4 * precision)
