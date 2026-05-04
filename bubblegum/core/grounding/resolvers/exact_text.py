"""
bubblegum/core/grounding/resolvers/exact_text.py
=================================================
ExactTextResolver — Tier 1, priority 30, web + mobile.

Searches the a11y snapshot for elements whose visible name / label matches
the instruction text exactly or case-insensitively.

Confidence:
  exact case-sensitive match    → 0.90
  exact case-insensitive match  → 0.82

ref format: text="Login"  (Playwright text locator)

Phase 1A — fully implemented.
"""

from __future__ import annotations

import re
import logging

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent
from bubblegum.core.grounding.signals import make_signals

logger = logging.getLogger(__name__)

# Same line regex as AccessibilityTreeResolver — parse role + name from snapshot
_SNAPSHOT_LINE_RE = re.compile(
    r"""
    ^[\s\-]*
    (?P<role>[a-zA-Z]+)
    (?:\s+"(?P<name>[^"]+)")?
    (?:\s+\[(?P<attrs>[^\]]*)\])?
    \s*$
    """,
    re.VERBOSE,
)


class ExactTextResolver(Resolver):
    """
    Matches elements by exact text label against instruction keywords.

    Returns text="<label>" style Playwright locator refs.
    Confidence is 0.90 for case-sensitive, 0.82 for case-insensitive.
    """

    name:       str       = "exact_text"
    priority:   int       = 30
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "low"
    tier:       int       = 1

    def required_context(self) -> list[str]:
        return ["a11y_snapshot"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        snapshot: str = intent.context["a11y_snapshot"]
        targets   = _extract_targets(intent.instruction)
        candidates: list[ResolvedTarget] = []
        seen: set[str] = set()
        raw_matches: list[tuple[str, float]] = []

        for line in snapshot.splitlines():
            m = _SNAPSHOT_LINE_RE.match(line)
            if not m:
                continue
            name = (m.group("name") or "").strip()
            if not name:
                continue

            confidence, matched = _match_confidence(name, targets)
            if confidence == 0.0:
                continue

            ref = f'text="{name}"'
            if ref in seen:
                continue  # deduplicate
            seen.add(ref)

            raw_matches.append((ref, confidence))
            candidates.append(
                ResolvedTarget(
                    ref=ref,
                    confidence=confidence,
                    resolver_name=self.name,
                    metadata={"matched_text": matched, "element_name": name},
                )
            )
            logger.debug("ExactText candidate: %s  conf=%.2f", ref, confidence)

        counts = {r:0 for r,_ in raw_matches}
        for r,_ in raw_matches: counts[r]+=1
        enriched=[]
        for t in candidates:
            conf = next((c for r,c in raw_matches if r==t.ref), t.confidence)
            tmatch = 1.0 if conf >= 0.90 else 0.82
            uniq = 1.0 if counts.get(t.ref,0)==1 else 0.6
            meta=dict(t.metadata); meta["signals"] = make_signals(text_match=tmatch, visibility=0.5, uniqueness=uniq, memory=0.0)
            enriched.append(t.model_copy(update={"metadata": meta}))
        return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_targets(instruction: str) -> list[str]:
    """
    Pull candidate target strings from the instruction.

    Strategy: try quoted phrases first, then quoted-word sequences,
    then individual meaningful tokens.
    Returns lower-stripped list of strings to match against.
    """
    # Quoted phrases: click "Login" or tap 'Submit'
    quoted = re.findall(r'["\']([^"\']+)["\']', instruction)
    if quoted:
        return [q.strip() for q in quoted]

    # Fall back to non-stopword tokens
    stopwords = {"click", "tap", "press", "select", "type", "enter", "the", "a", "an",
                 "on", "in", "into", "at", "to", "and", "or", "verify", "check",
                 "assert", "is", "are", "visible", "present"}
    tokens = re.findall(r"[a-zA-Z0-9']+", instruction)
    filtered = [t for t in tokens if t.lower() not in stopwords]
    return filtered if filtered else tokens


def _match_confidence(element_name: str, targets: list[str]) -> tuple[float, str]:
    """
    Return (confidence, matched_string) for the best match between
    element_name and the target strings extracted from the instruction.
    Returns (0.0, "") if no match.
    """
    for t in targets:
        # Case-sensitive exact
        if element_name == t:
            return (0.90, t)
        # Case-insensitive exact
        if element_name.lower() == t.lower():
            return (0.82, t)

    return (0.0, "")
