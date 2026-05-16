"""
bubblegum/core/grounding/resolvers/appium_hierarchy.py
=======================================================
AppiumHierarchyResolver — Tier 1 mobile resolver.

Parses the Appium XML element hierarchy (driver.page_source) to find elements
matching the step intent. Mobile equivalent of AccessibilityTreeResolver.

Matching strategy (in priority order for each candidate element):
  1. text attribute          — element label shown to the user
  2. content-desc attribute  — accessibility description (Android)
  3. resource-id attribute   — e.g. "com.example:id/login_btn"

Matching direction (both checked):
  - instruction contains element value  ("tap animation" contains "animation") ✅
  - element value contains instruction  ("animation" contains "tap animation") ✅
  This handles both "Tap Animation" → matches text="Animation" and
  "Login" → matches text="Login button".

ref format (JSON string to honour ResolvedTarget.ref: str schema):
  '{"by": "xpath", "value": "//android.widget.TextView[@text=\'Animation\']"}'

Confidence scoring:
  text match       → 0.92
  content-desc     → 0.85
  resource-id      → 0.75

required_context() returns [] so can_run() succeeds for all mobile intents.
resolve() handles missing hierarchy_xml gracefully by returning [].

Phase 4 — fully implemented.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import logging

from bubblegum.core.elements.graph import ElementGraph
from bubblegum.core.elements.graph_signals import GraphSignalInput, compute_graph_signals
from bubblegum.core.elements.normalized import normalize_mobile_hierarchy_node
from bubblegum.core.elements.query import build_graph_query_diagnostics
from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent
from bubblegum.core.grounding.signals import make_signals
from bubblegum.core.mobile.repeated_structure import disambiguate_within_repeated_region

logger = logging.getLogger(__name__)

_CONF_TEXT         = 0.92
_CONF_CONTENT_DESC = 0.85
_CONF_RESOURCE_ID  = 0.75


def _text_matches(instruction_lower: str, value: str) -> bool:
    """
    Return True if the instruction and element value overlap meaningfully.

    Checks both directions:
      1. value is contained in instruction  — "animation" in "tap animation"
      2. instruction is contained in value  — "login" in "login button"

    This handles action-prefixed instructions ("Tap X", "Click X", "Type X")
    where stripping the verb leaves just the target word.
    """
    value_lower = value.lower().strip()
    if not value_lower:
        return False
    return value_lower in instruction_lower or instruction_lower in value_lower


class AppiumHierarchyResolver(Resolver):
    """
    Parses Appium XML hierarchy and matches elements by text, content-desc,
    or resource-id against the step instruction.

    required_context() returns [] so can_run() succeeds for all mobile intents.
    resolve() returns [] gracefully when hierarchy_xml is absent from context.
    """

    name:       str = "appium_hierarchy"
    priority:   int = 20
    channels        = ["mobile"]
    cost_level: str = "low"
    tier:       int = 1

    def required_context(self) -> list[str]:
        # Empty — hierarchy_xml absence is handled inside resolve() so that
        # can_run() returns True for all eligible mobile intents and the resolver
        # appears correctly in ResolverRegistry.eligible_for().
        return []

    def supports(self, intent: StepIntent) -> bool:
        return intent.action_type in (
            "tap", "click", "type", "select", "scroll", "swipe", "verify", "extract"
        )

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """
        Parse the XML hierarchy and return all matching elements as ResolvedTargets.
        Returns [] immediately when hierarchy_xml is missing — no error raised.
        Matching is case-insensitive and bidirectional.
        """
        hierarchy_xml: str = intent.context.get("hierarchy_xml", "")
        if not hierarchy_xml:
            logger.debug("AppiumHierarchyResolver: no hierarchy_xml in context")
            return []

        instruction_lower = intent.instruction.lower().strip()

        try:
            root = ET.fromstring(hierarchy_xml)
        except ET.ParseError as exc:
            logger.warning("AppiumHierarchyResolver: XML parse error: %s", exc)
            return []

        candidates: list[ResolvedTarget] = []
        normalized_elements = []
        elements_by_ref: dict[str, object] = {}
        parent_lookup: dict[int, str] = {}
        children_lookup: dict[str, list[str]] = {}
        for parent in root.iter():
            pid = id(parent)
            parent_ref = _element_xpath_ref(parent)
            children = list(parent)
            if children:
                children_lookup[parent_ref] = [_element_xpath_ref(ch) for ch in children]
            for child in children:
                parent_lookup[id(child)] = parent_ref

        for element in root.iter():
            source_ref = _element_xpath_ref(element)
            normalized = normalize_mobile_hierarchy_node(
                {
                    "class": (element.get("class") or element.tag or "").strip(),
                    "text": (element.get("text") or "").strip(),
                    "content-desc": (element.get("content-desc") or "").strip(),
                    "resource-id": (element.get("resource-id") or "").strip(),
                    "bounds": (element.get("bounds") or "").strip(),
                    "enabled": (element.get("enabled") or "true").strip().lower() != "false",
                    "displayed": (element.get("visible-to-user") or "true").strip().lower() != "false",
                    "source_ref": source_ref,
                    "parent_id": parent_lookup.get(id(element)),
                    "children_ids": children_lookup.get(source_ref, []),
                },
                platform=intent.platform or "android",
                source_kind="appium_hierarchy",
            )
            normalized_elements.append(normalized)
            if normalized.source_ref:
                elements_by_ref[normalized.source_ref] = normalized
            result = self._match_element(element, instruction_lower, intent.action_type)
            if result is not None:
                candidates.append(result)
        graph = ElementGraph(normalized_elements) if normalized_elements else None
        relational_intent = intent.context.get("relational_intent")
        context_graph = intent.context.get("element_graph") or intent.context.get("graph")
        diagnostics = None
        if isinstance(context_graph, ElementGraph) and isinstance(relational_intent, dict):
            diagnostics = build_graph_query_diagnostics(context_graph, relational_intent, action_type=intent.action_type)

        repeated_diag = disambiguate_within_repeated_region(
            instruction=intent.instruction,
            target_candidates=candidates,
            anchor_candidates=[],
            elements=normalized_elements,
            graph=graph,
        ) if len(candidates) > 1 else None

        enriched: list[ResolvedTarget] = []
        for target in candidates:
            meta = dict(target.metadata)
            meta["graph_signals"] = compute_graph_signals(
                GraphSignalInput(
                    candidate_ref=target.ref,
                    candidate_text=str(meta.get("matched_value", "")),
                    candidate_role=str(meta.get("tag", "")),
                    instruction=intent.instruction,
                ),
                graph=graph,
                elements_by_ref=elements_by_ref,
            )
            if isinstance(diagnostics, dict):
                meta["graph_query_diagnostics"] = diagnostics
            if isinstance(repeated_diag, dict):
                safe_diag = {
                    "status": repeated_diag.get("status", "unknown"),
                    "region_type": repeated_diag.get("region_type", "unknown"),
                    "matched_region_count": int(repeated_diag.get("matched_region_count", 0)),
                    "candidate_count": int(repeated_diag.get("candidate_count", len(candidates))),
                    "anchor_hint_type": repeated_diag.get("anchor_hint_type", "none"),
                    "target_action_hint": repeated_diag.get("target_action_hint", "unknown"),
                    "reason": repeated_diag.get("reason", "unknown"),
                    "evidence": [str(v) for v in repeated_diag.get("evidence", [])],
                    "warnings": [str(v) for v in repeated_diag.get("warnings", [])],
                    "safe_metadata_only": True,
                }
                meta["repeated_region_diagnostics"] = safe_diag
            if repeated_diag and repeated_diag.get("status") == "resolved" and repeated_diag.get("selected_candidate_ref") == target.ref:
                meta["repeated_region_diagnostics"]["status"] = "resolved"
            enriched.append(target.model_copy(update={"metadata": meta}))

        logger.debug(
            "AppiumHierarchyResolver: found %d candidate(s) for %r",
            len(enriched),
            intent.instruction,
        )
        return enriched

    def _match_element(
        self,
        element: ET.Element,
        instruction_lower: str,
        action_type: str,
    ) -> ResolvedTarget | None:
        """
        Attempt to match a single XML element against the instruction.
        Checks in order: text → content-desc → resource-id.
        Uses bidirectional substring matching via _text_matches().
        """
        tag    = element.tag or ""
        widget_type = (element.get("class") or tag or "").strip()
        text   = (element.get("text") or "").strip()
        c_desc = (element.get("content-desc") or "").strip()
        res_id = (element.get("resource-id") or "").strip()
        bounds = element.get("bounds") or ""
        enabled_attr = (element.get("enabled") or "").strip().lower()
        visible_attr = (element.get("visible-to-user") or "").strip().lower()
        hidden_attr = (element.get("hidden") or "").strip().lower()
        explicitly_hidden = (
            enabled_attr == "false"
            or visible_attr == "false"
            or hidden_attr in ("true", "1")
        )
        visibility = 0.2 if explicitly_hidden else (1.0 if bounds else 0.8)

        # text match (highest confidence)
        if text and _text_matches(instruction_lower, text):
            xpath = _build_xpath(widget_type, "text", text)
            return ResolvedTarget(
                ref=json.dumps({"by": "xpath", "value": xpath}),
                confidence=_CONF_TEXT,
                resolver_name=self.name,
                metadata={
                    "signals": make_signals(text_match=0.92, role_match=_role_match_for_action(widget_type, action_type), visibility=visibility, uniqueness=0.8, memory=0.0),
                    "matched_attr": "text",
                    "matched_value": text,
                    "tag": widget_type,
                    "bounds": bounds,
                },
            )

        # content-desc match
        if c_desc and _text_matches(instruction_lower, c_desc):
            xpath = _build_xpath(widget_type, "content-desc", c_desc)
            return ResolvedTarget(
                ref=json.dumps({"by": "xpath", "value": xpath}),
                confidence=_CONF_CONTENT_DESC,
                resolver_name=self.name,
                metadata={
                    "signals": make_signals(text_match=0.85, role_match=_role_match_for_action(widget_type, action_type), visibility=visibility, uniqueness=0.8, memory=0.0),
                    "matched_attr": "content-desc",
                    "matched_value": c_desc,
                    "tag": widget_type,
                    "bounds": bounds,
                },
            )

        # resource-id match (strip package prefix for matching)
        if res_id:
            id_part = res_id.split("/")[-1] if "/" in res_id else res_id
            if _text_matches(instruction_lower, id_part) or _text_matches(instruction_lower, res_id):
                xpath = _build_xpath(widget_type, "resource-id", res_id)
                return ResolvedTarget(
                    ref=json.dumps({"by": "xpath", "value": xpath}),
                    confidence=_CONF_RESOURCE_ID,
                    resolver_name=self.name,
                    metadata={
                    "signals": make_signals(text_match=0.75, role_match=_role_match_for_action(widget_type, action_type), visibility=visibility, uniqueness=0.8, memory=0.0),
                        "matched_attr": "resource-id",
                        "matched_value": res_id,
                        "tag": widget_type,
                        "bounds": bounds,
                    },
                )

        return None


def _build_xpath(tag: str, attr: str, value: str) -> str:
    """
    Build an XPath expression to locate an element by attribute value.

    Example:
      tag="android.widget.TextView", attr="text", value="Animation"
      → //android.widget.TextView[@text='Animation']

    Single quotes in value are handled via XPath concat() to prevent injection.
    """
    if not tag:
        tag = "*"

    if "'" not in value:
        return f"//{tag}[@{attr}='{value}']"

    # Escape single quotes: split and rejoin with XPath concat()
    parts = value.split("'")
    concat_args = ", \"'\", ".join(f"'{p}'" for p in parts)
    return f"//{tag}[@{attr}=concat({concat_args})]"

def _role_match_for_action(tag: str, action_type: str) -> float:
    t = tag.lower()
    if action_type in ("tap", "click"):
        return 1.0 if any(x in t for x in ("button", "imagebutton", "textview")) else 0.4
    if action_type == "type":
        return 1.0 if "edittext" in t else 0.2
    if action_type == "verify":
        return 0.9 if any(x in t for x in ("textview", "edittext", "button")) else 0.5
    return 0.5


def _element_xpath_ref(element: ET.Element) -> str:
    widget_type = (element.get("class") or element.tag or "*").strip() or "*"
    text = (element.get("text") or "").strip()
    c_desc = (element.get("content-desc") or "").strip()
    if text:
        xpath = _build_xpath(widget_type, "text", text)
    elif c_desc:
        xpath = _build_xpath(widget_type, "content-desc", c_desc)
    else:
        xpath = f"//{widget_type}"
    return json.dumps({"by": "xpath", "value": xpath})
