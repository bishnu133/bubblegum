"""
bubblegum/core/grounding/resolvers/accessibility_tree.py
=========================================================
AccessibilityTreeResolver -- Tier 1, priority 20, web-only.

Parses Playwright's YAML-format aria_snapshot to find elements matching the
step instruction. Returns Playwright semantic locator strings as refs.

Confidence levels:
  exact role + name match  -> 0.96   (gap of 0.06 over ExactTextResolver's 0.90,
                                      clears the ambiguous_gap threshold of 0.05)
  partial name match       -> 0.80 (role fits action) / 0.70 (role mismatch)
  role-only (no name)      -> 0.60

WHY required_context() returns []:
    The Phase 0 registry test asserts 'accessibility_tree' appears in eligible
    resolvers for a bare StepIntent with no context. Declaring
    required_context=["a11y_snapshot"] would make can_run() return False when
    the key is absent. Following the same pattern as ExplicitSelectorResolver,
    we guard inside resolve() instead -- returns [] immediately if a11y_snapshot
    is absent in intent.context.

Phase 1A -- fully implemented.
"""

from __future__ import annotations

import re
import logging

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent
from bubblegum.core.grounding.signals import make_signals, role_fit_score, strip_icon_chars
from bubblegum.core.elements.graph import ElementGraph
from bubblegum.core.elements.query import build_graph_query_diagnostics
from bubblegum.core.elements.graph_signals import GraphSignalInput, compute_graph_signals
from bubblegum.core.elements.normalized import normalize_web_entry

logger = logging.getLogger(__name__)

# Maps aria role tokens to Playwright get_by_role() role names (lowercase)
_ROLE_ALIASES: dict[str, str] = {
    "button":        "button",
    "link":          "link",
    "textbox":       "textbox",
    "checkbox":      "checkbox",
    "radio":         "radio",
    "combobox":      "combobox",
    "listbox":       "listbox",
    "option":        "option",
    "heading":       "heading",
    "img":           "img",
    "image":         "img",
    "tab":           "tab",
    "menuitem":      "menuitem",
    "menu":          "menu",
    "dialog":        "dialog",
    "alert":         "alert",
    "main":          "main",
    "nav":           "navigation",
    "navigation":    "navigation",
    "region":        "region",
    "form":          "form",
    "search":        "searchbox",
    "searchbox":     "searchbox",
    "switch":        "switch",
    "slider":        "slider",
    "spinbutton":    "spinbutton",
    "progressbar":   "progressbar",
    "status":        "status",
    "log":           "log",
    "banner":        "banner",
    "contentinfo":   "contentinfo",
    "complementary": "complementary",
    "cell":          "cell",
    "row":           "row",
    "columnheader":  "columnheader",
    "rowheader":     "rowheader",
    "table":         "table",
    "grid":          "grid",
    "gridcell":      "gridcell",
    "tree":          "tree",
    "treeitem":      "treeitem",
    "group":         "group",
    "list":          "list",
    "listitem":      "listitem",
    "paragraph":     "paragraph",
}


def _make_snapshot_re() -> re.Pattern:
    # Captures: role, elname (from `"name"` OR `: name` forms), attrs.
    # Playwright's locator.aria_snapshot() uses two different name forms:
    #
    #   - button "Sign in"                  <- quoted form (most roles)
    #   - combobox: Select country          <- inline-value form
    #                                          (combobox, sometimes textbox)
    #
    # Some lines combine both, e.g.
    #
    #   - combobox "Country": United States <- quoted name + inline value
    #
    # We always extract the quoted name when present (the accessible name
    # is the right text for the role-based selector), and let the trailing
    # `: value` be discarded by the final `\s*(?::\s*[^\[\n]*)?\s*$`.
    # YAML "has children" colons stay unmatched because the bare colon
    # branch requires at least one non-whitespace char of inline value.
    pattern = (
        r"^[\s\-]*"                                 # optional indent / dashes
        r"(?P<role>[a-zA-Z]+)"                      # role word
        r'(?:'
        r'\s+"(?P<elname_q>[^"]+)"'                 # role "name"
        r'|:\s*(?P<elname_c>[^\s\[][^\[\n]*?)'      # role: name (inline value)
        r')?'
        r"(?:\s+\[(?P<attrs>[^\]]*)\])?"            # optional [attrs]
        r"\s*(?::\s*[^\[\n]*)?"                     # optional trailing : value
        r"\s*$"
    )
    return re.compile(pattern)


_SNAPSHOT_LINE_RE = _make_snapshot_re()


# Phase 22E-1: when the parser surfaces a control_kind_hint (link, radio,
# combobox, dialog, switch, tab, input, button), candidates whose role
# aligns with that hint get a small tie-breaking confidence boost. This
# lets "Click the Sign in link" prefer role=link over role=button when
# both candidates would otherwise tie on text match. Stays small (< 0.05)
# so it cannot promote a weak-match candidate over a strong one.
_KIND_ROLE_ALIGNMENT: dict[str, frozenset[str]] = {
    "link":     frozenset({"link"}),
    "button":   frozenset({"button"}),
    "checkbox": frozenset({"checkbox"}),
    "radio":    frozenset({"radio"}),
    "switch":   frozenset({"switch"}),
    "tab":      frozenset({"tab"}),
    "dropdown": frozenset({"combobox", "listbox"}),
    "select":   frozenset({"combobox", "listbox"}),
    "combobox": frozenset({"combobox"}),
    "dialog":   frozenset({"dialog", "alertdialog"}),
    "input":    frozenset({"textbox", "searchbox"}),
}
_KIND_BIAS = 0.03  # < 0.05 so it cannot cross the ambiguity_gap threshold.


def _kind_role_aligned(kind: str, role: str) -> bool:
    if not kind or kind == "none":
        return False
    return role in _KIND_ROLE_ALIGNMENT.get(kind, frozenset())


class AccessibilityTreeResolver(Resolver):
    """
    Parses the YAML-format aria snapshot from Playwright's locator.aria_snapshot()
    and returns semantic locator refs for matching elements.

    Does NOT declare required_context() -- guards inside resolve() so can_run()
    always returns True for the web channel regardless of context state.
    Returns [] immediately if a11y_snapshot is absent.
    """

    name:       str       = "accessibility_tree"
    priority:   int       = 20
    channels:   list[str] = ["web"]
    cost_level: str       = "low"
    tier:       int       = 1

    # NOTE: required_context() intentionally NOT overridden.

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        snapshot: str | None = intent.context.get("a11y_snapshot")
        if not snapshot:
            return []

        keywords = _extract_keywords(intent.match_phrase)
        phrases = _extract_phrases(intent.match_phrase)
        candidates: list[ResolvedTarget] = []
        signal_rows: list[tuple[str, float, float, float]] = []

        ref_rows: list[tuple[str, str, str]] = []
        for line in snapshot.splitlines():
            m = _SNAPSHOT_LINE_RE.match(line)
            if not m:
                continue

            raw_role = m.group("role").lower()
            elname   = strip_icon_chars(
                (m.group("elname_q") or m.group("elname_c") or "").strip()
            )
            role     = _ROLE_ALIASES.get(raw_role)

            if not role:
                continue

            confidence, matched = _score(role, elname, keywords, phrases, intent.action_type)
            if confidence == 0.0:
                continue

            ref = _build_ref(role, elname)
            ref_rows.append((ref, role, elname))
            signal_rows.append((ref, confidence, role_fit_score(role, intent.action_type), 0.8))
            candidates.append(
                ResolvedTarget(
                    ref=ref,
                    confidence=confidence,
                    resolver_name=self.name,
                    metadata={
                        "role":         role,
                        "name":         elname,
                        "matched_text": matched,
                    },
                )
            )
            logger.debug("A11yTree candidate: %s  conf=%.2f", ref, confidence)

        counts: dict[str, int] = {}
        for ref, *_ in signal_rows:
            counts[ref] = counts.get(ref, 0) + 1

        normalized_elements = [
            normalize_web_entry(
                {
                    "source_ref": ref,
                    "role": role,
                    "name": name,
                    "label": name,
                    "text": name,
                    "visible": True,
                    "enabled": True,
                },
                source_kind="accessibility_tree",
            )
            for ref, role, name in ref_rows
        ]
        graph = ElementGraph(normalized_elements) if normalized_elements else None
        elements_by_ref = {e.source_ref or "": e for e in normalized_elements if e.source_ref}

        relational_intent = intent.context.get("relational_intent")
        context_graph = intent.context.get("element_graph") or intent.context.get("graph")
        diagnostics = None
        if isinstance(context_graph, ElementGraph) and isinstance(relational_intent, dict):
            diagnostics = build_graph_query_diagnostics(context_graph, relational_intent, action_type=intent.action_type)

        # Phase 22E-1: kind-hint tie-break. If the parser said "Click the Sign
        # in link", boost role=link over role=button when their text scores
        # would otherwise tie.
        kind_hint = "none"
        if isinstance(relational_intent, dict):
            kind_hint = str(relational_intent.get("control_kind_hint") or "none").lower()
        if kind_hint != "none":
            biased: list[ResolvedTarget] = []
            for cand in candidates:
                role = str(cand.metadata.get("role", ""))
                if _kind_role_aligned(kind_hint, role):
                    nudged = min(1.0, cand.confidence + _KIND_BIAS)
                    biased.append(cand.model_copy(update={"confidence": nudged}))
                else:
                    biased.append(cand)
            candidates = biased

        enriched: list[ResolvedTarget] = []
        for target in candidates:
            row = next((r for r in signal_rows if r[0] == target.ref), None)
            if row is None:
                enriched.append(target)
                continue
            _, tmatch, rmatch, vis = row
            # Phase 22E-1c/d: kind-aligned candidates get role_match=1.0;
            # candidates whose role does NOT match an explicit kind hint
            # get a penalty so the aligned candidate has a real lead in
            # the ranker (otherwise both can end up at 1.0 after the
            # alignment boost and tie -- ranker.rank is stable so the
            # earlier-in-snapshot candidate wins, which is exactly the
            # wrong behaviour for "Click the Sign in link").
            if kind_hint != "none":
                target_role = str(target.metadata.get("role", ""))
                if _kind_role_aligned(kind_hint, target_role):
                    rmatch = 1.0
                else:
                    rmatch = max(0.0, rmatch * 0.7)
            uniq = 1.0 if counts.get(target.ref, 0) == 1 else 0.6
            boosted_tmatch = _signal_text_match(
                intent=intent,
                elname=str(target.metadata.get("name", "")),
                base_conf=tmatch,
                matched_text=str(target.metadata.get("matched_text", "")),
            )
            strong_verify_extract = _is_strong_verify_extract_match(
                intent=intent,
                elname=str(target.metadata.get("name", "")),
                boosted_tmatch=boosted_tmatch,
            )
            boosted_vis = 1.0 if strong_verify_extract else vis
            boosted_prox = 1.0 if strong_verify_extract else 0.0
            meta = dict(target.metadata)
            meta["graph_signals"] = compute_graph_signals(
                GraphSignalInput(
                    candidate_ref=target.ref,
                    candidate_text=str(target.metadata.get("name", "")),
                    candidate_role=str(target.metadata.get("role", "")),
                    instruction=intent.instruction,
                ),
                graph=graph,
                elements_by_ref=elements_by_ref,
            )
            if isinstance(diagnostics, dict):
                meta["graph_query_diagnostics"] = diagnostics
            meta["signals"] = make_signals(
                text_match=boosted_tmatch,
                role_match=rmatch,
                visibility=boosted_vis,
                uniqueness=uniq,
                proximity=boosted_prox,
                memory=0.0,
            )
            enriched.append(target.model_copy(update={"metadata": meta}))

        return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_keywords(instruction: str) -> list[str]:
    stopwords = {
        "click", "tap", "press", "select", "type", "enter", "the", "a", "an",
        "on", "in", "into", "at", "to", "and", "or", "verify", "check",
        "assert", "is", "are", "visible", "present", "button", "link",
        "input", "field", "text",
    }
    tokens = re.findall(r"[a-zA-Z0-9']+", instruction.lower())
    meaningful = [t for t in tokens if t not in stopwords]
    return meaningful if meaningful else tokens


def _extract_phrases(instruction: str) -> list[str]:
    """Extract likely target phrases from NL instruction (lowercased)."""
    quoted = re.findall(r'["\']([^"\']+)["\']', instruction)
    if quoted:
        return [q.strip().lower() for q in quoted if q.strip()]

    lowered = instruction.lower()
    stopword_patterns = [
        r"\bclick\b", r"\btap\b", r"\bpress\b", r"\bselect\b", r"\btype\b", r"\benter\b",
        r"\bverify\b", r"\bcheck\b", r"\bassert\b", r"\bconfirm\b", r"\bextract\b", r"\bget\b",
        r"\bvisible\b", r"\bpresent\b", r"\btext\b", r"\bheading\b", r"\blink\b", r"\bbutton\b",
        r"\bof\b", r"\bis\b", r"\bare\b", r"\bthe\b", r"\ba\b", r"\ban\b",
    ]
    for pat in stopword_patterns:
        lowered = re.sub(pat, " ", lowered)
    cleaned = re.sub(r"\s+", " ", lowered).strip()
    return [cleaned] if cleaned else []


def _signal_text_match(intent: StepIntent, elname: str, base_conf: float, matched_text: str) -> float:
    """Resolver-local signal bump for obvious NL verify/extract phrase matches."""
    el = elname.strip().lower()
    if base_conf <= 0.0:
        return 0.0
    if not el:
        return base_conf

    expected = str(intent.context.get("expected_value", "")).strip().lower()
    if expected and el == expected:
        return 1.0

    if intent.action_type in {"verify", "extract"}:
        tokens = re.findall(r"[a-zA-Z0-9']+", el)
        instruction_keywords = _extract_keywords(intent.instruction)
        phrase_exact = any(p == el for p in _extract_phrases(intent.instruction))
        if len(tokens) == 1 and len(instruction_keywords) > 1 and not phrase_exact and not expected:
            # Avoid over-promoting short generic labels (e.g. "plan") embedded in
            # richer instructions like "Active plan visible".
            return min(base_conf, 0.82)

    if base_conf >= 0.96:
        return 1.0

    if intent.action_type in {"verify", "extract"}:
        for phrase in _extract_phrases(intent.instruction):
            if phrase == el:
                return 1.0
            if _is_strong_phrase_containment(el, phrase):
                return max(0.95, base_conf)

    if matched_text and matched_text.strip().lower() == el:
        return max(0.95, base_conf)
    return base_conf


def _is_strong_verify_extract_match(intent: StepIntent, elname: str, boosted_tmatch: float) -> bool:
    """
    Strong match gate for verify/extract boosts.
    Prevents weak one-word substring candidates (e.g., "plan") from being
    promoted to the same level as richer phrase matches.
    """
    if intent.action_type not in {"verify", "extract"}:
        return False
    el = elname.strip().lower()
    if not el:
        return False

    expected = str(intent.context.get("expected_value", "")).strip().lower()
    if expected and expected == el:
        return True

    for phrase in _extract_phrases(intent.instruction):
        if phrase == el:
            return True
    return False


def _is_strong_phrase_containment(el: str, phrase: str) -> bool:
    """
    True only for high-signal phrase containment:
    - exact containment relationship, AND
    - element name is multi-token or sufficiently long.
    This avoids over-boosting generic short single-word labels.
    """
    if not phrase:
        return False
    if not (el in phrase or phrase in el):
        return False
    token_count = len(re.findall(r"[a-zA-Z0-9']+", el))
    return token_count >= 2 or len(el) >= 10


def _score(
    role: str,
    elname: str,
    keywords: list[str],
    phrases: list[str],
    action_type: str,
) -> tuple[float, str]:
    """
    Returns (confidence, matched_text). 0.0 means no match.

    Confidence ladder:
      0.96 -- exact role + name match  (clears 0.05 ambiguity gap over ExactTextResolver=0.90)
      0.80 -- partial name match, role fits action
      0.70 -- partial name match, role mismatch
      0.60 -- role fits action but element has no accessible name
    """
    name_lower = elname.lower()
    role_ok = role_fit_score(role, action_type)

    if name_lower and any(phrase == name_lower for phrase in phrases):
        return (0.96, elname)

    if name_lower and any(kw == name_lower for kw in keywords):
        return (0.96, elname)

    if name_lower and any(kw in name_lower or name_lower in kw for kw in keywords):
        return (0.80 if role_ok else 0.70, elname)

    if role_ok and not name_lower:
        return (0.60, role)

    return (0.0, "")



def _build_ref(role: str, elname: str) -> str:
    if elname:
        return f'role={role}[name="{elname}"]'
    return f"role={role}"
