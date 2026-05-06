from __future__ import annotations

import re


def infer_action_type(instruction: str, kwargs: dict) -> str:
    """Infer action_type from kwargs or instruction text."""
    if "action_type" in kwargs:
        return kwargs["action_type"]
    lowered = instruction.lower()
    if any(w in lowered for w in ("type", "enter", "fill", "input")):
        return "type"
    if any(w in lowered for w in ("select", "choose", "pick")):
        return "select"
    if any(w in lowered for w in ("scroll",)):
        return "scroll"
    if any(w in lowered for w in ("verify", "check", "assert", "visible", "present")):
        return "verify"
    if any(w in lowered for w in ("extract", "get", "read", "fetch")):
        return "extract"
    return "click"


def extract_expected(instruction: str) -> str:
    """Pull key noun phrase from a verify instruction."""
    return re.sub(
        r"^(verify|check|assert|confirm|ensure|see|that)\s+",
        "",
        instruction,
        flags=re.IGNORECASE,
    ).strip()
