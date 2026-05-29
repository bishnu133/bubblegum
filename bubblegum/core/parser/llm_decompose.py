"""
bubblegum/core/parser/llm_decompose.py
=======================================
LLM-backed instruction decomposition — the AI fallback for natural-language
parsing when the deterministic grammar in ``decompose()`` cannot cleanly split
an instruction into {action, target, value}.

Design:
  - This is a *fallback*, consistent with Bubblegum's fallback-first posture.
    The SDK only calls it when ParsedIntent.confident is False AND AI is enabled
    AND the cost policy allows it.
  - The model is asked for strict JSON. Any failure (network, bad JSON, missing
    keys) returns None so the deterministic path is never broken.
  - No screenshots or DOM are sent — only the short instruction string. This is
    cheap (a few tokens) and privacy-safe.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You convert a single UI test step written in plain English into structured "
    "JSON. Respond with ONLY a JSON object, no prose. Keys:\n"
    '  "action_type": one of "click", "tap", "type", "select", "scroll", '
    '"verify", "extract".\n'
    '  "target_phrase": the visible label/description of the element to act on '
    "(string), or null if none.\n"
    '  "input_value": the text to type or option to select (string), or null if '
    "the action takes no value.\n"
    "Do not invent values. If the step says to type something, put exactly that "
    "text in input_value and the field name in target_phrase."
)

_ALLOWED_ACTIONS = {"click", "tap", "type", "select", "scroll", "verify", "extract"}


@dataclass
class LLMParsedIntent:
    action_type: str | None
    target_phrase: str | None
    input_value: str | None


async def llm_decompose(instruction: str, provider) -> LLMParsedIntent | None:
    """Ask the model to decompose an instruction. Returns None on any failure.

    Args:
        instruction: the raw NL step.
        provider:    a ModelProvider with an async ``complete()`` method.
    """
    if provider is None:
        return None

    prompt = f"Step: {instruction}\nReturn the JSON object."
    try:
        result = await provider.complete(prompt, system=_SYSTEM, response_format="json")
    except Exception as exc:  # noqa: BLE001 - fallback must never raise
        logger.warning("llm_decompose: provider call failed, using deterministic parse: %s", exc)
        return None

    raw = (getattr(result, "text", None) or "").strip()
    if not raw:
        return None

    data = _safe_json(raw)
    if data is None:
        logger.warning("llm_decompose: model returned non-JSON; using deterministic parse")
        return None

    action = data.get("action_type")
    if isinstance(action, str):
        action = action.strip().lower()
        if action not in _ALLOWED_ACTIONS:
            action = None
    else:
        action = None

    return LLMParsedIntent(
        action_type=action,
        target_phrase=_as_str(data.get("target_phrase")),
        input_value=_as_str(data.get("input_value")),
    )


def _as_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return str(value)


def _safe_json(raw: str) -> dict | None:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Tolerate models that wrap JSON in code fences or extra text.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
    return parsed if isinstance(parsed, dict) else None
