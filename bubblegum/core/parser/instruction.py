from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedIntent:
    """Structured decomposition of a natural-language step.

    Attributes:
        action_type:   click | tap | type | select | scroll | verify | extract
        target_phrase: the element description to find (e.g. "Username"), or None
        input_value:   the value to type/select (e.g. "tomsmith"), or None
        confident:     True when the rule-based grammar matched cleanly. When
                       False, the SDK may escalate to an LLM parser.
    """

    action_type: str
    target_phrase: str | None
    input_value: str | None
    confident: bool


# Verbs we strip from the front of an instruction to isolate the target phrase.
_LEADING_VERBS = (
    "click", "tap", "press", "select", "choose", "pick", "type", "enter",
    "fill", "input", "verify", "check", "uncheck", "tick", "untick", "toggle",
    "upload", "attach", "open", "follow", "assert", "confirm", "ensure", "see",
    "extract", "get", "read", "fetch", "scroll", "to", "on", "the",
)

# "Enter <value> into <target>" grammar for type/select/upload actions.
_VALUE_INTO_TARGET_RE = re.compile(
    r'^\s*(?:enter|type|fill|input|select|choose|pick|set|upload|attach)\s+'
    r'(?:"([^"]+)"|\'([^\']+)\'|(.+?))\s+'
    r'(?:into|in|on|to|from|as|=)\s+(?:the\s+)?(.+?)\s*$',
    re.IGNORECASE,
)

_LEADING_VERB_RE = re.compile(
    r"^\s*(?:" + "|".join(_LEADING_VERBS) + r")\b\s*"
    r"(?:(?:the|a|an)\b\s*)?",
    re.IGNORECASE,
)

# Trailing widget-kind words to strip from a target phrase so that
# "Click the Sign in link" yields target="Sign in" (not "Sign in link")
# and "Choose Blue radio button" yields target="Blue". Matches one suffix
# at the end of the phrase; the control_kind_hint already carries the
# widget identity separately on the relational intent.
_TRAILING_WIDGET_SUFFIX_RE = re.compile(
    r"\s+(?:link|button|checkbox|radio(?:\s+button)?|switch|toggle|dropdown|tab)"
    r"\s*[\.!?]?\s*$",
    re.IGNORECASE,
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    out = value.strip(" .,:;\t\n\r\"'")
    out = re.sub(r"\s+", " ", out).strip()
    return out or None


def _strip_widget_suffix(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = _TRAILING_WIDGET_SUFFIX_RE.sub("", value)
    cleaned = _clean(stripped)
    return cleaned if cleaned else _clean(value)


def decompose(instruction: str, kwargs: dict | None = None) -> ParsedIntent:
    """Split a natural-language instruction into (action, target, value).

    Pure rule-based; never calls a model. Returns confident=False when the
    grammar is ambiguous so the SDK can optionally escalate to an LLM parser.
    """
    kwargs = kwargs or {}
    action = infer_action_type(instruction, kwargs)
    text = instruction.strip()

    explicit_value = kwargs.get("input_value", kwargs.get("value"))

    if action in {"type", "select", "upload"}:
        m = _VALUE_INTO_TARGET_RE.match(text)
        if m:
            value = m.group(1) or m.group(2) or m.group(3)
            target = m.group(4)
            return ParsedIntent(action, _strip_widget_suffix(target), _clean(value), confident=True)

        # "Type tomsmith" with the target supplied separately, or value via kwargs.
        stripped = _LEADING_VERB_RE.sub("", text, count=1)
        if explicit_value is not None:
            # Caller supplied the value; remaining text is the target.
            target = _strip_widget_suffix(stripped) or _strip_widget_suffix(text)
            return ParsedIntent(action, target, explicit_value, confident=bool(_clean(stripped)))
        # Widget-suffix fallback for "Choose Blue radio button" style: the
        # only target-identifying signal is the trailing widget word, so use
        # it to confidently isolate the label.
        if action == "select" and _TRAILING_WIDGET_SUFFIX_RE.search(stripped):
            target = _strip_widget_suffix(stripped)
            if target:
                return ParsedIntent(action, target, None, confident=True)
        # No target separator and no explicit value — ambiguous; let the LLM decide.
        return ParsedIntent(action, None, None, confident=False)

    # click / tap / verify / extract / scroll: target is the text after the verb.
    target = _LEADING_VERB_RE.sub("", text, count=1)
    target = _strip_widget_suffix(target)
    return ParsedIntent(action, target, explicit_value, confident=bool(target))


def infer_action_type(instruction: str, kwargs: dict) -> str:
    """Infer action_type from kwargs or instruction text."""
    if "action_type" in kwargs:
        return kwargs["action_type"]
    lowered = instruction.lower()
    # Explicit verify cues come first so they shadow ambiguous overlap with
    # "check" as a verb (e.g. "Check that login is visible" → verify).
    if any(w in lowered for w in ("verify", "assert", "visible", "present", "displayed", "shown")):
        return "verify"
    if re.search(r'\bcheck\s+(?:that|if)\b', lowered):
        return "verify"
    if re.search(r'\b(upload|attach)\b', lowered):
        return "upload"
    if re.search(r'\b(uncheck|untick)\b', lowered):
        return "uncheck"
    if re.search(r'\b(tick|toggle)\b', lowered) or re.search(r'\bcheck\b', lowered):
        return "check"
    if any(w in lowered for w in ("type", "enter", "fill", "input")):
        return "type"
    if any(w in lowered for w in ("select", "choose", "pick")):
        return "select"
    if "scroll" in lowered:
        return "scroll"
    if any(w in lowered for w in ("extract", "get", "read", "fetch")):
        return "extract"
    if any(w in lowered for w in ("tap", "touch")):
        return "tap"
    return "click"


def extract_expected(instruction: str) -> str:
    """Pull the expected text or state from a verify instruction.

    Strips leading verify verbs and trailing state phrases so that
    'Verify Hello World is visible' → 'Hello World'.
    """
    text = re.sub(
        r"^(verify|check|assert|confirm|ensure|see|that)\s+",
        "",
        instruction,
        flags=re.IGNORECASE,
    ).strip()
    # Strip common trailing state words that describe the assertion, not the content.
    text = re.sub(
        r"\s+(is\s+)?(visible|present|shown|displayed|enabled|checked|selected|active)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return text


def _base_relational_payload() -> dict[str, Any]:
    return {
        "primary_target_text": None,
        "relation_type": "none",
        "anchor_text": None,
        "scope_type": "none",
        "scope_label": None,
        "control_kind_hint": "none",
        "mobile_attr_preference": "none",
        "ambiguity_policy": "fail_on_ambiguous",
    }


def _clean_fragment(value: str | None) -> str | None:
    if value is None:
        return None
    out = value.strip(" .,:;!?\t\n\r\"'")
    out = re.sub(r"\s+", " ", out).strip()
    return out or None


def parse_relational_intent(instruction: str, action_type: str | None = None) -> dict[str, Any] | None:
    """Parse conservative relational metadata hints from instruction text.

    Rule-based only. Returns None if no safe MVP pattern matches.
    """
    text = instruction.strip()
    lowered = text.casefold()

    # Guard: intentionally defer complex nested/multi-anchor relational phrasing.
    if re.search(r"\b(for|from|in)\b.*\b(for|from|in)\b", lowered):
        return None

    # 1) "for <anchor>" => same_row_as_text
    m_for = re.search(r"\bfor\s+(.+?)\s*[\.!?]?\s*$", text, flags=re.IGNORECASE)
    if m_for:
        anchor = _clean_fragment(m_for.group(1))
        if anchor:
            payload = _base_relational_payload()
            payload["relation_type"] = "same_row_as_text"
            payload["anchor_text"] = anchor
            return payload

    # 2) "in the confirmation modal" / "in modal" => within_modal
    m_modal_labeled = re.search(r"\bin\s+(?:the\s+)?(.+?)\s+modal\b", text, flags=re.IGNORECASE)
    if m_modal_labeled:
        label = _clean_fragment(m_modal_labeled.group(1))
        payload = _base_relational_payload()
        payload["relation_type"] = "within_modal"
        payload["scope_type"] = "modal"
        payload["scope_label"] = f"{label} modal" if label else None
        return payload

    if re.search(r"\bin\s+modal\b", lowered):
        payload = _base_relational_payload()
        payload["relation_type"] = "within_modal"
        payload["scope_type"] = "modal"
        return payload

    # 3) "from/in the <label> dropdown" => within_region + dropdown
    m_dropdown = re.search(r"\b(?:from|in)\s+(?:the\s+)?(.+?)\s+dropdown\b", text, flags=re.IGNORECASE)
    if m_dropdown:
        label = _clean_fragment(m_dropdown.group(1))
        if label:
            payload = _base_relational_payload()
            payload["relation_type"] = "within_region"
            payload["scope_type"] = "region"
            payload["scope_label"] = label
            payload["control_kind_hint"] = "dropdown"
            return payload

    # 4) "check/uncheck/tick/untick <label>" / "checkbox <label>" => label_for + checkbox
    # Guard: "Check that/if/whether ..." is a verify-style instruction, not a
    # checkbox action — skip this rule in that case.
    checkbox_verbs = ("check", "uncheck", "tick", "untick", "checkbox")
    is_verify_check = bool(re.match(r"^check\s+(?:that|if|whether)\b", text, flags=re.IGNORECASE))
    if (
        action_type != "verify"
        and not is_verify_check
        and (action_type in {"check", "uncheck"} or any(lowered.startswith(v + " ") for v in checkbox_verbs))
    ):
        m_checkbox = re.match(
            r"^(?:check|uncheck|tick|untick|checkbox)\s+(?:the\s+)?(.+?)\s*[\.!?]?\s*$",
            text,
            flags=re.IGNORECASE,
        )
        if m_checkbox:
            label = _clean_fragment(m_checkbox.group(1))
            if label:
                payload = _base_relational_payload()
                payload["relation_type"] = "label_for"
                payload["control_kind_hint"] = "checkbox"
                payload["primary_target_text"] = label
                payload["scope_type"] = "label"
                return payload

    # 5) "toggle <label>" => label_for + switch (Phase 22D-2)
    if lowered.startswith("toggle "):
        m_toggle = re.match(
            r"^toggle\s+(?:the\s+)?(.+?)\s*[\.!?]?\s*$",
            text,
            flags=re.IGNORECASE,
        )
        if m_toggle:
            label = _clean_fragment(m_toggle.group(1))
            if label:
                payload = _base_relational_payload()
                payload["relation_type"] = "label_for"
                payload["control_kind_hint"] = "switch"
                payload["primary_target_text"] = label
                payload["scope_type"] = "label"
                return payload

    # 6) "<verb> <label> link" => label_for + link (Phase 22D-2)
    m_link = re.match(
        r"^\s*(?:click|tap|press|open|follow)\s+(?:the\s+)?(.+?)\s+link\s*[\.!?]?\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if m_link:
        label = _clean_fragment(m_link.group(1))
        if label:
            payload = _base_relational_payload()
            payload["relation_type"] = "label_for"
            payload["control_kind_hint"] = "link"
            payload["primary_target_text"] = label
            payload["scope_type"] = "label"
            return payload

    # 7) "<verb> <label> radio [button]" => label_for + radio (Phase 22D-2)
    m_radio = re.match(
        r"^\s*(?:click|tap|press|select|choose|pick)\s+(?:the\s+)?(.+?)\s+radio(?:\s+button)?\s*[\.!?]?\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if m_radio:
        label = _clean_fragment(m_radio.group(1))
        if label:
            payload = _base_relational_payload()
            payload["relation_type"] = "label_for"
            payload["control_kind_hint"] = "radio"
            payload["primary_target_text"] = label
            payload["scope_type"] = "label"
            return payload

    # 8) "select/choose/pick <value> from <label>" without "dropdown" suffix
    # => label_for + dropdown hint (Phase 22D-2)
    m_select_from = re.match(
        r"^\s*(?:select|choose|pick)\s+"
        r"(?:\"[^\"]+\"|\'[^\']+\'|.+?)\s+"
        r"from\s+(?:the\s+)?(.+?)\s*[\.!?]?\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if m_select_from:
        label = _clean_fragment(m_select_from.group(1))
        if label:
            payload = _base_relational_payload()
            payload["relation_type"] = "label_for"
            payload["control_kind_hint"] = "dropdown"
            payload["primary_target_text"] = label
            payload["scope_type"] = "label"
            return payload

    return None
