"""
bubblegum/core/grounding/resolvers/appium_hierarchy.py
=======================================================
AppiumHierarchyResolver — Tier 1 mobile resolver.

Parses the Appium XML element hierarchy (driver.page_source) to find elements
matching the step intent. Mobile equivalent of AccessibilityTreeResolver.

Cross-platform attributes
-------------------------
Android (UiAutomator2) and iOS (XCUITest) expose different attribute names for
the same concepts. The resolver reads BOTH schemas and maps them onto one
unified view so matching works identically on either platform:

  concept        Android              iOS (XCUIElementType…)
  -------------  -------------------  -----------------------
  visible text   text                 label
  a11y / id      content-desc         name   (accessibilityIdentifier|label)
  field value    (n/a)                value
  widget type    class                type
  geometry       bounds="[x,y][x,y]"  x / y / width / height
  enabled        enabled              enabled
  visible        visible-to-user      visible

On React-Native iOS a ``testID`` becomes the XCUITest ``name``, but when the
element also has a visible label XCUITest often surfaces that label as ``name``
too — so matching by human text ("View daily summary") succeeds even when a
testID-based locator would not.

Matching strategy (in priority order for each candidate element):
  1. text / label attribute  — element label shown to the user
  2. content-desc / name      — accessibility description / identifier
  3. resource-id attribute   — e.g. "com.example:id/login_btn"
  4. value attribute (iOS)   — current field value

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
from bubblegum.core.mobile.icon_detection import resolve_icon_target_hint

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


# Leading action verbs stripped before scoring exactness, so a verb-prefixed
# instruction ("Tap Login") still counts as an exact match of the label
# ("Login") — mirroring the parser's target_phrase decomposition for the cases
# where the raw instruction reaches the resolver undecomposed.
_ACTION_VERBS = frozenset({
    "tap", "click", "press", "select", "choose", "type", "enter", "set",
    "open", "toggle", "check", "uncheck", "hit", "touch", "on",
})


def _strip_leading_verb(instruction_lower: str) -> str:
    parts = instruction_lower.split()
    if len(parts) > 1 and parts[0] in _ACTION_VERBS:
        return " ".join(parts[1:]).strip()
    return instruction_lower


def _match_quality(instruction_lower: str, value: str) -> float:
    """Rate how tight a text match is, in (0, 1] — 1.0 for an exact match.

    A bare substring match is not enough to disambiguate lookalikes: the
    instruction "Allow" matches BOTH an "Allow" button and a "Don't Allow"
    button (both contain "allow"). Scoring exactness lets the exact label win.
    Longer partial overlaps (value nearly equals the instruction) score higher
    than short fragments buried in a long label. A leading action verb is
    stripped first so "Tap Login" scores as an exact match of "Login".
    """
    v = value.lower().strip()
    if not v:
        return 0.0
    for candidate in (instruction_lower, _strip_leading_verb(instruction_lower)):
        if v == candidate:
            return 1.0
    best = 0.0
    for candidate in (instruction_lower, _strip_leading_verb(instruction_lower)):
        if v in candidate or candidate in v:
            longer = max(len(v), len(candidate))
            shorter = min(len(v), len(candidate))
            best = max(best, shorter / longer if longer else 0.0)
    return best


def _scale_by_quality(base: float, quality: float) -> float:
    """Scale a confidence/signal by match quality, leaving exact matches (q=1.0)
    at ``base`` and easing partial matches down enough to rank below an exact
    match without dropping them below resolution thresholds."""
    if quality >= 1.0:
        return base
    return round(base * (0.7 + 0.3 * quality), 4)


def _is_ios_element(element: ET.Element, platform: str) -> bool:
    """True when the node belongs to an iOS/XCUITest hierarchy.

    Detected from the intent platform, the XCUIElementType tag/type, or the
    presence of iOS-only attributes — so a mixed or platform-less context still
    routes each node correctly.
    """
    if (platform or "").lower() == "ios":
        return True
    tag = element.tag or ""
    if tag.startswith("XCUIElementType"):
        return True
    if (element.get("type") or "").startswith("XCUIElementType"):
        return True
    return False


def _ios_bounds(element: ET.Element) -> str:
    """Render iOS x/y/width/height attributes as an Android-style bounds string.

    XCUITest reports geometry as four integer attributes rather than the
    ``[x,y][x,y]`` string Android uses. Emitting that string lets the shared
    ``NormalizedBounds`` parser and visibility scoring treat both platforms the
    same. Returns "" when geometry is absent or zero-sized.
    """
    try:
        x = int(float(element.get("x", "0") or 0))
        y = int(float(element.get("y", "0") or 0))
        w = int(float(element.get("width", "0") or 0))
        h = int(float(element.get("height", "0") or 0))
    except (TypeError, ValueError):
        return ""
    if w <= 0 and h <= 0:
        return ""
    return f"[{x},{y}][{x + w},{y + h}]"


def _unified_attrs(element: ET.Element, platform: str = "") -> dict:
    """Read an element's attributes into one platform-neutral view.

    Android and iOS attribute names are normalized onto the same keys
    (``widget_type``/``text``/``content_desc``/``resource_id``/``value``/
    ``bounds``/``enabled``/``visible``/``clickable``) so every downstream
    consumer — matching, xpath building, the normalized graph — works from a
    single shape regardless of platform.
    """
    tag = element.tag or ""
    if _is_ios_element(element, platform):
        widget_type = (element.get("type") or element.get("class") or tag or "").strip()
        label = (element.get("label") or "").strip()
        name = (element.get("name") or "").strip()
        return {
            "ios": True,
            "widget_type": widget_type,
            # Visible label is the iOS analogue of Android's `text`.
            "text": label,
            # `name` is the accessibility id (often the visible label on RN iOS).
            "content_desc": name,
            "resource_id": "",
            "value": (element.get("value") or "").strip(),
            "bounds": (element.get("bounds") or "").strip() or _ios_bounds(element),
            "enabled_attr": (element.get("enabled") or "").strip().lower(),
            "visible_attr": (element.get("visible") or "").strip().lower(),
            "hidden_attr": (element.get("hidden") or "").strip().lower(),
            # iOS has no `clickable`; control-ness is inferred from the type.
            "clickable": widget_type.lower().endswith(("button", "cell", "link")),
        }
    widget_type = (element.get("class") or tag or "").strip()
    return {
        "ios": False,
        "widget_type": widget_type,
        "text": (element.get("text") or "").strip(),
        "content_desc": (element.get("content-desc") or "").strip(),
        "resource_id": (element.get("resource-id") or "").strip(),
        "value": "",
        "bounds": (element.get("bounds") or "").strip(),
        "enabled_attr": (element.get("enabled") or "").strip().lower(),
        "visible_attr": (element.get("visible-to-user") or "").strip().lower(),
        "hidden_attr": (element.get("hidden") or "").strip().lower(),
        "clickable": (element.get("clickable") or "").strip().lower() == "true",
    }


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

        instruction_lower = intent.match_phrase.lower().strip()

        # M4: the UI toolkit (Compose/Flutter/RN/SwiftUI/native), detected in
        # the adapter and threaded through app_state, tunes role scoring below.
        app_state = intent.context.get("app_state")
        ui_framework_meta = app_state.get("ui_framework") if isinstance(app_state, dict) else None
        ui_framework = ""
        if isinstance(ui_framework_meta, dict):
            ui_framework = str(ui_framework_meta.get("framework") or "")

        try:
            root = ET.fromstring(hierarchy_xml)
        except ET.ParseError as exc:
            logger.warning("AppiumHierarchyResolver: XML parse error: %s", exc)
            return []

        platform = intent.platform or "android"
        candidates: list[ResolvedTarget] = []
        normalized_elements = []
        elements_by_ref: dict[str, object] = {}
        parent_lookup: dict[int, str] = {}
        children_lookup: dict[str, list[str]] = {}
        for parent in root.iter():
            pid = id(parent)
            parent_ref = _element_xpath_ref(parent, platform)
            children = list(parent)
            if children:
                children_lookup[parent_ref] = [_element_xpath_ref(ch, platform) for ch in children]
            for child in children:
                parent_lookup[id(child)] = parent_ref

        for element in root.iter():
            source_ref = _element_xpath_ref(element, platform)
            attrs = _unified_attrs(element, platform)
            normalized = normalize_mobile_hierarchy_node(
                {
                    "class": attrs["widget_type"] or element.tag or "",
                    "text": attrs["text"],
                    "content-desc": attrs["content_desc"],
                    "resource-id": attrs["resource_id"],
                    "bounds": attrs["bounds"],
                    "enabled": attrs["enabled_attr"] != "false",
                    "displayed": attrs["visible_attr"] != "false",
                    "attributes": {"clickable": attrs["clickable"]},
                    "source_ref": source_ref,
                    "parent_id": parent_lookup.get(id(element)),
                    "children_ids": children_lookup.get(source_ref, []),
                },
                platform=platform,
                source_kind="appium_hierarchy",
            )
            normalized_elements.append(normalized)
            if normalized.source_ref:
                elements_by_ref[normalized.source_ref] = normalized
            result = self._match_element(attrs, instruction_lower, intent.action_type, ui_framework=ui_framework)
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


        icon_diag = None
        if candidates:
            icon_diag = resolve_icon_target_hint(
                instruction=intent.instruction,
                candidates=candidates,
                elements=normalized_elements,
                graph=graph,
                repeated_region_diagnostics=repeated_diag,
            )
            if isinstance(icon_diag, dict) and icon_diag.get("status") == "resolved" and icon_diag.get("selected_candidate_ref"):
                selected_ref = icon_diag.get("selected_candidate_ref")
                candidates = [c for c in candidates if c.ref == selected_ref] or candidates
        enriched: list[ResolvedTarget] = []
        for target in candidates:
            meta = dict(target.metadata)
            if isinstance(ui_framework_meta, dict) and ui_framework_meta.get("framework"):
                # Surface the detected toolkit (+ any limits) on every candidate
                # so reports/explain show why scoring was tuned the way it was.
                meta["ui_framework"] = {
                    "framework": ui_framework_meta.get("framework"),
                    "confidence": ui_framework_meta.get("confidence"),
                    "limits": list(ui_framework_meta.get("limits") or []),
                }
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
            if isinstance(icon_diag, dict):
                safe_icon = {
                    "status": icon_diag.get("status", "unknown"),
                    "icon_hint_type": icon_diag.get("icon_hint_type", "unknown"),
                    "target_icon": icon_diag.get("target_icon", "unknown"),
                    "candidate_count": int(icon_diag.get("candidate_count", len(candidates))),
                    "matched_candidate_count": int(icon_diag.get("matched_candidate_count", 0)),
                    "reason": icon_diag.get("reason", "unknown"),
                    "evidence": [str(v) for v in icon_diag.get("evidence", [])],
                    "warnings": [str(v) for v in icon_diag.get("warnings", [])],
                    "safe_metadata_only": True,
                }
                meta["icon_detection"] = safe_icon
            enriched.append(target.model_copy(update={"metadata": meta}))

        logger.debug(
            "AppiumHierarchyResolver: found %d candidate(s) for %r",
            len(enriched),
            intent.instruction,
        )
        return enriched

    def _match_element(
        self,
        attrs: dict,
        instruction_lower: str,
        action_type: str,
        ui_framework: str = "",
    ) -> ResolvedTarget | None:
        """
        Attempt to match a single element against the instruction.
        Checks in order: text/label → content-desc/name → resource-id → value.
        Uses bidirectional substring matching via _text_matches().

        ``attrs`` is the platform-neutral view from :func:`_unified_attrs`, so
        the same matching runs against Android and iOS hierarchies.

        ``ui_framework`` (M4) tunes role scoring: Compose/RN render tappable
        controls as generic clickable View/ViewGroup nodes, which would
        otherwise be down-ranked for tap/click.
        """
        widget_type = attrs["widget_type"]
        text   = attrs["text"]
        c_desc = attrs["content_desc"]
        res_id = attrs["resource_id"]
        value  = attrs["value"]
        bounds = attrs["bounds"]
        clickable = attrs["clickable"]
        explicitly_hidden = (
            attrs["enabled_attr"] == "false"
            or attrs["visible_attr"] == "false"
            or attrs["hidden_attr"] in ("true", "1")
        )
        visibility = 0.2 if explicitly_hidden else (1.0 if bounds else 0.8)

        ios = attrs["ios"]
        # XPath attribute names differ per platform: iOS matches on the
        # `label`/`name`/`value` attributes, Android on `text`/`content-desc`.
        text_attr = "label" if ios else "text"
        desc_attr = "name" if ios else "content-desc"

        # text / label match (highest confidence)
        if text and _text_matches(instruction_lower, text):
            q = _match_quality(instruction_lower, text)
            xpath = _build_xpath(widget_type, text_attr, text)
            return ResolvedTarget(
                ref=json.dumps({"by": "xpath", "value": xpath}),
                confidence=_scale_by_quality(_CONF_TEXT, q),
                resolver_name=self.name,
                metadata={
                    "signals": make_signals(text_match=_scale_by_quality(0.92, q), role_match=_role_match_for_action(widget_type, action_type, ui_framework=ui_framework, clickable=clickable), visibility=visibility, uniqueness=0.8, memory=0.0),
                    "matched_attr": text_attr,
                    "matched_value": text,
                    "match_quality": q,
                    "tag": widget_type,
                    "bounds": bounds,
                },
            )

        # content-desc / name (accessibility) match
        if c_desc and _text_matches(instruction_lower, c_desc):
            q = _match_quality(instruction_lower, c_desc)
            xpath = _build_xpath(widget_type, desc_attr, c_desc)
            return ResolvedTarget(
                ref=json.dumps({"by": "xpath", "value": xpath}),
                confidence=_scale_by_quality(_CONF_CONTENT_DESC, q),
                resolver_name=self.name,
                metadata={
                    "signals": make_signals(text_match=_scale_by_quality(0.85, q), role_match=_role_match_for_action(widget_type, action_type, ui_framework=ui_framework, clickable=clickable), visibility=visibility, uniqueness=0.8, memory=0.0),
                    "matched_attr": desc_attr,
                    "matched_value": c_desc,
                    "match_quality": q,
                    "tag": widget_type,
                    "bounds": bounds,
                },
            )

        # resource-id match (Android; strip package prefix for matching)
        if res_id:
            id_part = res_id.split("/")[-1] if "/" in res_id else res_id
            if _text_matches(instruction_lower, id_part) or _text_matches(instruction_lower, res_id):
                xpath = _build_xpath(widget_type, "resource-id", res_id)
                return ResolvedTarget(
                    ref=json.dumps({"by": "xpath", "value": xpath}),
                    confidence=_CONF_RESOURCE_ID,
                    resolver_name=self.name,
                    metadata={
                    "signals": make_signals(text_match=0.75, role_match=_role_match_for_action(widget_type, action_type, ui_framework=ui_framework, clickable=clickable), visibility=visibility, uniqueness=0.8, memory=0.0),
                        "matched_attr": "resource-id",
                        "matched_value": res_id,
                        "tag": widget_type,
                        "bounds": bounds,
                    },
                )

        # value match (iOS text fields / labelled controls)
        if value and _text_matches(instruction_lower, value):
            q = _match_quality(instruction_lower, value)
            xpath = _build_xpath(widget_type, "value", value)
            return ResolvedTarget(
                ref=json.dumps({"by": "xpath", "value": xpath}),
                confidence=_scale_by_quality(_CONF_CONTENT_DESC, q),
                resolver_name=self.name,
                metadata={
                    "signals": make_signals(text_match=_scale_by_quality(0.8, q), role_match=_role_match_for_action(widget_type, action_type, ui_framework=ui_framework, clickable=clickable), visibility=visibility, uniqueness=0.8, memory=0.0),
                    "matched_attr": "value",
                    "matched_value": value,
                    "match_quality": q,
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

_GENERIC_VIEW_TAGS = ("view", "viewgroup", "composeview")
# Frameworks whose tappable controls render as generic clickable View nodes.
_GENERIC_CONTROL_FRAMEWORKS = {"jetpack_compose", "react_native"}


def _role_match_for_action(
    tag: str, action_type: str, *, ui_framework: str = "", clickable: bool = False
) -> float:
    t = tag.lower()
    # iOS XCUIElementType* names collapse to the same keywords Android uses:
    #   XCUIElementTypeButton   -> "button"      XCUIElementTypeTextField -> "textfield"
    #   XCUIElementTypeStaticText -> "statictext" (label)  XCUIElementTypeCell -> "cell"
    if action_type in ("tap", "click"):
        if any(x in t for x in ("button", "imagebutton", "textview", "cell", "link", "statictext")):
            return 1.0
        # M4: Compose / React Native expose tappable controls as generic
        # clickable View/ViewGroup nodes (no "button"/"textview" in the class),
        # which would otherwise be down-ranked. Treat a clickable generic node
        # as a real control for those toolkits. Additive — native scoring (no
        # ui_framework) is unchanged.
        if (
            ui_framework in _GENERIC_CONTROL_FRAMEWORKS
            and clickable
            and any(x in t for x in _GENERIC_VIEW_TAGS)
        ):
            return 0.9
        return 0.4
    if action_type == "type":
        return 1.0 if any(x in t for x in ("edittext", "textfield", "securetextfield")) else 0.2
    if action_type == "verify":
        return 0.9 if any(x in t for x in ("textview", "edittext", "button", "statictext", "textfield")) else 0.5
    return 0.5


def _element_xpath_ref(element: ET.Element, platform: str = "") -> str:
    attrs = _unified_attrs(element, platform)
    widget_type = attrs["widget_type"] or element.tag or "*"
    text = attrs["text"]
    c_desc = attrs["content_desc"]
    ios = attrs["ios"]
    if text:
        xpath = _build_xpath(widget_type, "label" if ios else "text", text)
    elif c_desc:
        xpath = _build_xpath(widget_type, "name" if ios else "content-desc", c_desc)
    else:
        xpath = f"//{widget_type}"
    return json.dumps({"by": "xpath", "value": xpath})
