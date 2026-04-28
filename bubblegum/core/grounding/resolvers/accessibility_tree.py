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
    # Built as a plain string to avoid any ambiguity with raw-string escaping.
    # Captures three named groups: role, elname (element name), attrs.
    # Example lines matched:
    #   - button "Login"
    #     - textbox "Username"
    #   - heading "My App" [level=1]
    #   - button
    pattern = (
        r"^[\s\-]*"                     # optional indent / dashes
        r"(?P<role>[a-zA-Z]+)"          # role word
        r'(?:\s+"(?P<elname>[^"]+)")?'  # optional  "quoted name"
        r"(?:\s+\[(?P<attrs>[^\]]*)\])?" # optional [attrs]
        r"\s*$"
    )
    return re.compile(pattern)


_SNAPSHOT_LINE_RE = _make_snapshot_re()


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

        keywords = _extract_keywords(intent.instruction)
        candidates: list[ResolvedTarget] = []

        for line in snapshot.splitlines():
            m = _SNAPSHOT_LINE_RE.match(line)
            if not m:
                continue

            raw_role = m.group("role").lower()
            elname   = (m.group("elname") or "").strip()
            role     = _ROLE_ALIASES.get(raw_role)

            if not role:
                continue

            confidence, matched = _score(role, elname, keywords, intent.action_type)
            if confidence == 0.0:
                continue

            ref = _build_ref(role, elname)
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

        return candidates


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


def _score(
    role: str,
    elname: str,
    keywords: list[str],
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
    role_ok = _role_fits_action(role, action_type)

    if name_lower and any(kw == name_lower for kw in keywords):
        return (0.96, elname)

    if name_lower and any(kw in name_lower or name_lower in kw for kw in keywords):
        return (0.80 if role_ok else 0.70, elname)

    if role_ok and not name_lower:
        return (0.60, role)

    return (0.0, "")


def _role_fits_action(role: str, action_type: str) -> bool:
    click_roles  = {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch"}
    type_roles   = {"textbox", "searchbox", "combobox", "spinbutton"}
    select_roles = {"combobox", "listbox", "option"}
    mapping: dict[str, set[str] | None] = {
        "click":   click_roles,
        "tap":     click_roles,
        "type":    type_roles,
        "select":  select_roles,
        "verify":  None,
        "extract": None,
    }
    allowed = mapping.get(action_type)
    return allowed is None or role in allowed


def _build_ref(role: str, elname: str) -> str:
    if elname:
        return f'role={role}[name="{elname}"]'
    return f"role={role}"
