"""
bubblegum/core/grounding/resolvers/semantic.py
==============================================
SemanticResolver — Tier 2, priority 47, web + mobile, cost_level=medium.

Embedding-based label matching that catches *meaning-level* drift the
edit-distance FuzzyTextResolver misses — "Submit" -> "Continue", "Delete" ->
"Move to Trash", "Sign in" -> "Access your account". It runs after fuzzy (which
short-circuits Tier 2 on a strong lexical hit) and before the costlier LLM tier,
so it only fires on the harder cases and resolves them faster/cheaper than an
LLM call.

Dormant by default: no embedding provider is wired unless the team configures
ai.embedding_model or injects one via configure_embedding_provider(). When
dormant, supports() returns False and the resolver is skipped entirely — zero
network, zero cost, no behaviour change.

Generic across applications: it reads the same accessibility snapshot the fuzzy
and a11y-tree resolvers use (web *and* mobile), emits the same role=/text= ref
format, and feeds the shared signal/ranking machinery — so it composes with
memory caching, ambiguity checks, and self-healing exactly like every other
resolver.
"""

from __future__ import annotations

import logging
import re

from bubblegum.core import embedding_cache
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.grounding.signals import make_signals, role_fit_score, strip_icon_chars
from bubblegum.core.grounding.resolvers.fuzzy_text import (
    _ROLE_ALIASES,
    _SNAPSHOT_LINE_RE,
)
from bubblegum.core.schemas import ResolvedTarget, StepIntent

logger = logging.getLogger(__name__)

# Cap the number of labels embedded per screen so a pathological page (thousands
# of nodes) cannot blow up a single embeddings request. On larger pages the
# labels are pre-filtered to those sharing at least one token with the query.
_MAX_EMBED_CANDIDATES = 200


class SemanticResolver(Resolver):
    name:       str       = "semantic"
    priority:   int       = 47          # after fuzzy_text (45), before llm (50)
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "medium"    # embeddings cost ~nothing but may hit the network
    tier:       int       = 2

    def __init__(self, provider=None, *, min_similarity: float = 0.72) -> None:
        self._provider = provider
        self._min_similarity = float(min_similarity)

    def set_provider(self, provider, *, min_similarity: float | None = None) -> None:
        """Inject/clear the embedding provider (and optionally the threshold)."""
        self._provider = provider
        if min_similarity is not None:
            self._min_similarity = float(min_similarity)

    @property
    def has_provider(self) -> bool:
        return self._provider is not None

    def supports(self, intent: StepIntent) -> bool:
        # Dormant unless an embedding provider is wired — skipped entirely.
        return self._provider is not None

    def required_context(self) -> list[str]:
        return ["a11y_snapshot"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        if self._provider is None:
            return []
        snapshot = intent.context.get("a11y_snapshot") or ""
        if not snapshot.strip():
            return []

        query = self._query_text(intent)
        if not query:
            return []

        labels = _extract_labels(snapshot)
        if not labels:
            return []

        labels = _prefilter(query, labels, _MAX_EMBED_CANDIDATES)

        try:
            vectors = embedding_cache.embed_cached(self._provider, [query] + [l[1] for l in labels])
        except Exception as exc:  # noqa: BLE001 — degrade to the LLM tier, never raise
            logger.warning("SemanticResolver: embedding call failed: %s", exc)
            return []

        query_vec = vectors[0]
        if not query_vec:
            return []

        # Score every label; keep those at/above the similarity floor.
        scored: list[tuple[str, str, float]] = []  # (role, elname, sim)
        for (role, elname), vec in zip(labels, vectors[1:]):
            sim = embedding_cache.cosine(query_vec, vec)
            if sim >= self._min_similarity:
                scored.append((role, elname, sim))

        if not scored:
            return []

        # Uniqueness: a label that appears once is a stronger signal than a
        # repeated one.
        name_counts: dict[str, int] = {}
        for _, elname, _ in scored:
            name_counts[elname] = name_counts.get(elname, 0) + 1

        out: list[ResolvedTarget] = []
        seen: set[str] = set()
        for raw_role, elname, sim in scored:
            role = _ROLE_ALIASES.get(raw_role)
            ref = f'role={role}[name="{elname}"]' if role else f'text="{elname}"'
            if ref in seen:
                continue
            seen.add(ref)

            role_match = role_fit_score(role or "", intent.action_type) if role else 0.0
            uniqueness = 1.0 if name_counts.get(elname, 0) == 1 else 0.6
            signals = make_signals(
                text_match=sim,
                role_match=role_match,
                visibility=0.85,
                uniqueness=uniqueness,
                proximity=0.5,
                memory=0.0,
            )
            out.append(
                ResolvedTarget(
                    ref=ref,
                    confidence=round(sim, 4),
                    resolver_name=self.name,
                    metadata={
                        "matched_text":  elname,
                        "element_name":  elname,
                        "semantic_similarity": round(sim, 4),
                        "role":          role or raw_role,
                        "source":        "semantic",
                        "signals":       signals,
                    },
                )
            )
            logger.debug("Semantic candidate: %s  sim=%.3f", ref, sim)
        return out

    # ------------------------------------------------------------------

    def _query_text(self, intent: StepIntent) -> str:
        """The phrase to embed — prefer the parsed target, then the match phrase.

        Full phrases embed better than single tokens (embeddings capture word
        order and context), so we use the whole target phrase when available.
        """
        for cand in (intent.target_phrase, getattr(intent, "match_phrase", None), intent.instruction):
            if cand and str(cand).strip():
                return str(cand).strip()
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_labels(snapshot: str) -> list[tuple[str, str]]:
    """Parse (raw_role, element_name) pairs from an aria snapshot.

    Mirrors FuzzyTextResolver's line parsing so both resolvers see the same
    elements. Only named elements are returned (semantic match needs a label).
    """
    labels: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for line in snapshot.splitlines():
        m = _SNAPSHOT_LINE_RE.match(line)
        if not m:
            continue
        raw_role = m.group("role").lower()
        elname = strip_icon_chars((m.group("elname_q") or m.group("elname_c") or "").strip())
        if not elname:
            continue
        key = (raw_role, elname)
        if key in seen:
            continue
        seen.add(key)
        labels.append(key)
    return labels


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _prefilter(query: str, labels: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    """Bound the embedding batch on very large pages.

    Under the limit, embed everything (best recall). Over it, keep labels that
    share at least one token with the query, then fill up to the limit — so we
    never silently drop a lexically-overlapping candidate.
    """
    if len(labels) <= limit:
        return labels
    q_tokens = _tokens(query)
    overlapping = [l for l in labels if _tokens(l[1]) & q_tokens]
    if len(overlapping) >= limit:
        return overlapping[:limit]
    rest = [l for l in labels if l not in overlapping]
    return (overlapping + rest)[:limit]
