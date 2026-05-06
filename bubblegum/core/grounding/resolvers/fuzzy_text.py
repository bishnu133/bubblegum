"""
bubblegum/core/grounding/resolvers/fuzzy_text.py
=================================================
FuzzyTextResolver — Tier 2, priority 45, web + mobile, cost_level=low.

Matches elements in the accessibility snapshot using edit-distance similarity
(difflib.SequenceMatcher) and a built-in synonym table to catch label drift
like "Login" → "Sign In".

Confidence ladder:
  near-exact  (ratio >= 0.85)  → 0.82
  good match  (ratio >= 0.65)  → 0.72
  weak match  (ratio >= 0.50)  → 0.62
  no match    (ratio <  0.50)  → element skipped

required_context() returns ["a11y_snapshot"] — resolver is skipped by the
registry when the snapshot is absent, which is the correct Tier 2 behaviour.

ref format: role=button[name="Sign In"]  (same as AccessibilityTreeResolver)
            text="Sign In"               (fallback when role is unknown/absent)

Phase 1B — fully implemented.
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import NamedTuple

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent
from bubblegum.core.grounding.signals import make_signals

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synonym table — bidirectional pairs (both directions are tried)
# ---------------------------------------------------------------------------
_SYNONYMS: list[tuple[str, str]] = [
    ("login",    "sign in"),
    ("log in",   "sign in"),
    ("logout",   "sign out"),
    ("log out",  "sign out"),
    ("register", "sign up"),
    ("signup",   "sign up"),
    ("sign up",  "create account"),
    ("delete",   "remove"),
    ("remove",   "delete"),
    ("edit",     "modify"),
    ("modify",   "edit"),
    ("back",     "return"),
    ("return",   "go back"),
    ("submit",   "send"),
    ("send",     "submit"),
    ("ok",       "confirm"),
    ("confirm",  "ok"),
    ("yes",      "confirm"),
    ("cancel",   "dismiss"),
    ("dismiss",  "close"),
    ("close",    "cancel"),
    ("search",   "find"),
    ("find",     "search"),
    ("next",     "continue"),
    ("continue", "proceed"),
    ("save",     "apply"),
    ("apply",    "save"),
    ("upload",   "attach"),
    ("attach",   "upload"),
    ("download", "export"),
    ("export",   "download"),
]

# Build a lookup: lowercased token → set of synonym tokens
_SYNONYM_MAP: dict[str, set[str]] = {}
for _a, _b in _SYNONYMS:
    _SYNONYM_MAP.setdefault(_a, set()).add(_b)
    _SYNONYM_MAP.setdefault(_b, set()).add(_a)

# ---------------------------------------------------------------------------
# Snapshot line parser (same pattern as AccessibilityTreeResolver)
# ---------------------------------------------------------------------------
_SNAPSHOT_LINE_RE = re.compile(
    r"""
    ^[\s\-]*
    (?P<role>[a-zA-Z]+)
    (?:\s+"(?P<elname>[^"]+)")?
    (?:\s+\[(?P<attrs>[^\]]*)\])?
    \s*:?\s*$
    """,
    re.VERBOSE,
)

_ROLE_ALIASES: dict[str, str] = {
    "button":   "button",
    "link":     "link",
    "textbox":  "textbox",
    "checkbox": "checkbox",
    "radio":    "radio",
    "combobox": "combobox",
    "listbox":  "listbox",
    "option":   "option",
    "heading":  "heading",
    "tab":      "tab",
    "menuitem": "menuitem",
    "switch":   "switch",
}

# Confidence thresholds and values
_NEAR_EXACT_RATIO = 0.85
_GOOD_MATCH_RATIO = 0.65
_WEAK_MATCH_RATIO = 0.50

_NEAR_EXACT_CONF  = 0.82
_GOOD_MATCH_CONF  = 0.72
_WEAK_MATCH_CONF  = 0.62


class FuzzyTextResolver(Resolver):
    """
    Fuzzy label matching for Tier 2 fallback.

    Uses edit-distance ratio (difflib.SequenceMatcher) plus synonym expansion
    to catch label drift like "Login" -> "Sign In" or "Submit" -> "Send".

    Returns role=<role>[name="<label>"] refs compatible with PlaywrightAdapter.
    """

    name:       str       = "fuzzy_text"
    priority:   int       = 45
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "low"
    tier:       int       = 2

    def required_context(self) -> list[str]:
        return ["a11y_snapshot"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        snapshot: str = intent.context["a11y_snapshot"]
        targets = _extract_targets(intent.instruction)

        candidates: list[ResolvedTarget] = []
        seen: set[str] = set()
        rows: list[tuple[str,float,float]] = []

        for line in snapshot.splitlines():
            m = _SNAPSHOT_LINE_RE.match(line)
            if not m:
                continue

            raw_role = m.group("role").lower()
            elname   = (m.group("elname") or "").strip()

            if not elname:
                continue  # fuzzy matching requires an accessible name

            confidence, matched, ratio = _best_match(elname, targets)
            if confidence == 0.0:
                continue

            role = _ROLE_ALIASES.get(raw_role)
            if role:
                ref = f'role={role}[name="{elname}"]'
            else:
                ref = f'text="{elname}"'

            if ref in seen:
                continue
            seen.add(ref)

            role_match = 1.0 if role else 0.0
            rows.append((ref, ratio, role_match))
            candidates.append(
                ResolvedTarget(
                    ref=ref,
                    confidence=confidence,
                    resolver_name=self.name,
                    metadata={
                        "matched_text": matched,
                        "element_name": elname,
                        "fuzzy_ratio":  round(ratio, 3),
                        "role":         role or raw_role,
                    },
                )
            )
            logger.debug(
                "FuzzyText candidate: %s  conf=%.2f  ratio=%.2f  matched=%r",
                ref, confidence, ratio, matched,
            )

        counts={r:0 for r,_,_ in rows}
        for r,_,_ in rows: counts[r]+=1
        enriched=[]
        for t in candidates:
            row = next((x for x in rows if x[0]==t.ref), None)
            if row is None:
                enriched.append(t); continue
            _, ratio, rmatch = row
            uniq = 1.0 if counts.get(t.ref,0)==1 else 0.6
            meta=dict(t.metadata); meta["signals"] = make_signals(text_match=ratio, role_match=rmatch, visibility=0.5, uniqueness=uniq, memory=0.0)
            enriched.append(t.model_copy(update={"metadata": meta}))
        return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_targets(instruction: str) -> list[str]:
    """Pull candidate target strings from the NL instruction."""
    quoted = re.findall(r'["\']([^"\']+)["\']', instruction)
    if quoted:
        return [q.strip() for q in quoted]

    stopwords = {
        "click", "tap", "press", "select", "type", "enter", "the", "a", "an",
        "on", "in", "into", "at", "to", "and", "or", "verify", "check",
        "assert", "is", "are", "visible", "present", "button", "link",
        "input", "field", "text",
    }
    tokens = re.findall(r"[a-zA-Z0-9']+", instruction)
    filtered = [t for t in tokens if t.lower() not in stopwords]
    return filtered if filtered else tokens


def _similarity_ratio(a: str, b: str) -> float:
    """Case-insensitive SequenceMatcher ratio."""
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _expand_with_synonyms(term: str) -> list[str]:
    """Return term plus all known synonyms (lowercased)."""
    lower = term.lower()
    expanded = [lower]
    expanded.extend(_SYNONYM_MAP.get(lower, []))
    return expanded


def _best_match(elname: str, targets: list[str]) -> tuple[float, str, float]:
    """
    Compare elname against all targets (including synonyms).

    Returns (confidence, best_matched_target, best_ratio).
    Returns (0.0, "", 0.0) if no target meets the weak threshold.
    """
    best_ratio  = 0.0
    best_target = ""

    for raw_target in targets:
        for candidate in _expand_with_synonyms(raw_target):
            ratio = _similarity_ratio(elname, candidate)
            if ratio > best_ratio:
                best_ratio  = ratio
                best_target = raw_target

    if best_ratio >= _NEAR_EXACT_RATIO:
        return (_NEAR_EXACT_CONF, best_target, best_ratio)
    if best_ratio >= _GOOD_MATCH_RATIO:
        return (_GOOD_MATCH_CONF, best_target, best_ratio)
    if best_ratio >= _WEAK_MATCH_RATIO:
        return (_WEAK_MATCH_CONF, best_target, best_ratio)

    return (0.0, "", best_ratio)
