"""
bubblegum/core/grounding/resolvers/llm_grounding.py
=====================================================
LLMGroundingResolver — Tier 3, priority 50, web + mobile, cost_level=high.

Sends a filtered subset of the a11y snapshot to a configured LLM text model
and parses the JSON response into a ResolvedTarget.

Filtering strategy:
  Only lines whose role token matches the expected action_type are sent to the
  model. This reduces token cost significantly vs sending the full tree.

LLM prompt contract:
  Model must return a single JSON object:
    {"ref": "role=button[name='...']", "confidence": 0.0-1.0, "reasoning": "..."}

  ref format must match PlaywrightAdapter._resolve_locator() conventions:
    role=<role>[name="<n>"]   -> Playwright semantic locator
    text=<text>                  -> Playwright text locator

Safety rules:
  - If JSON parse fails: return [] (never raise)
  - If confidence < reject_threshold (0.50): return []
  - Provider injected at construction time -> testable without real API

Phase 2 — fully implemented.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import concurrent.futures

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.models.base import ModelProvider
from bubblegum.core.schemas import ResolvedTarget, StepIntent

logger = logging.getLogger(__name__)

_ACTION_ROLES: dict[str, set[str]] = {
    "click":   {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"},
    "tap":     {"button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"},
    "type":    {"textbox", "searchbox", "combobox", "spinbutton", "input"},
    "select":  {"combobox", "listbox", "option", "select"},
    "scroll":  set(),
    "verify":  set(),
    "extract": set(),
}

_REJECT_THRESHOLD = 0.50

_SYSTEM_PROMPT = """\
You are a UI element grounding assistant for automated testing.
You receive a filtered accessibility tree (Playwright aria_snapshot YAML format)
and a natural language test instruction. Identify the best matching element.

Return ONLY a JSON object — no markdown, no extra text:
{
  "ref": "<playwright_locator_string>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}

ref format rules:
  - Elements with a name: role=<role>[name="<element name>"]
  - Text content only:    text=<visible text>
  - Prefer role= over text= when both apply.
  - Use exact name as it appears in the tree.

confidence rules:
  0.90+      : exact or near-exact name match
  0.70-0.89  : partial or synonym match
  0.50-0.69  : plausible but uncertain
  below 0.50 : do not guess — return confidence 0.0

If no match: {"ref": "", "confidence": 0.0, "reasoning": "no match"}
"""


class LLMGroundingResolver(Resolver):
    """
    AI fallback resolver. Sends a filtered a11y snapshot to an LLM and parses
    the JSON response into a ResolvedTarget.

    Provider is injected — not created internally — making this fully testable
    without a real API key.
    """

    name:       str       = "llm_grounding"
    priority:   int       = 50
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "high"
    tier:       int       = 3

    def __init__(self, provider: ModelProvider | None = None) -> None:
        self._provider = provider

    def required_context(self) -> list[str]:
        return ["a11y_snapshot"]

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """
        Sync entry point required by the Resolver ABC.
        Delegates to _resolve_async via a thread pool to avoid event-loop conflicts.
        """
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, self._resolve_async(intent))
                return future.result()
        except Exception as exc:
            logger.error("LLMGroundingResolver.resolve() failed: %s", exc)
            return []

    async def resolve_async(self, intent: StepIntent) -> list[ResolvedTarget]:
        """
        Async variant — preferred in async GroundingEngine contexts.
        Avoids thread-pool overhead when already inside an event loop.
        """
        return await self._resolve_async(intent)

    # ------------------------------------------------------------------

    async def _resolve_async(self, intent: StepIntent) -> list[ResolvedTarget]:
        if self._provider is None:
            logger.debug("LLMGroundingResolver: no provider configured — skipping (registry stub mode)")
            return []

        snapshot: str | None = intent.context.get("a11y_snapshot")
        if not snapshot:
            return []

        filtered = _filter_snapshot(snapshot, intent.action_type)
        if not filtered.strip():
            logger.debug("LLMGroundingResolver: no relevant lines after filtering")
            return []

        prompt = _build_prompt(intent.instruction, filtered)
        logger.debug(
            "LLMGroundingResolver calling provider=%s model=%s action=%s",
            self._provider.provider_name, self._provider.model, intent.action_type,
        )

        try:
            result = await self._provider.complete(
                prompt,
                system=_SYSTEM_PROMPT,
                response_format="json",
            )
        except Exception as exc:
            logger.error("LLMGroundingResolver provider call failed: %s", exc)
            return []

        return _parse_response(result.text, self.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_snapshot(snapshot: str, action_type: str) -> str:
    """Filter snapshot lines to only roles relevant for this action_type."""
    allowed_roles = _ACTION_ROLES.get(action_type, set())
    if not allowed_roles:
        return snapshot

    role_re = re.compile(r"^[\s\-]*(?P<role>[a-zA-Z]+)(?:\s+|$)")
    filtered_lines = [
        line for line in snapshot.splitlines()
        if (m := role_re.match(line)) and m.group("role").lower() in allowed_roles
    ]
    return "\n".join(filtered_lines)


def _build_prompt(instruction: str, filtered_snapshot: str) -> str:
    return (
        f"Test instruction: {instruction}\n\n"
        f"Accessibility tree (filtered):\n{filtered_snapshot}\n\n"
        f"Return the best matching element as JSON."
    )


def _parse_response(text: str, resolver_name: str) -> list[ResolvedTarget]:
    """Parse LLM JSON response. Returns [] on any failure — never raises."""
    if not text or not text.strip():
        logger.warning("LLMGroundingResolver: empty response from provider")
        return []

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("LLMGroundingResolver: JSON parse failed — %s", exc)
        return []

    ref        = (data.get("ref") or "").strip()
    confidence = float(data.get("confidence", 0.0))
    reasoning  = data.get("reasoning", "")

    if not ref or confidence < _REJECT_THRESHOLD:
        logger.debug(
            "LLMGroundingResolver: discarding ref=%r confidence=%.2f", ref, confidence
        )
        return []

    return [
        ResolvedTarget(
            ref=ref,
            confidence=round(confidence, 4),
            resolver_name=resolver_name,
            metadata={
                "reasoning": reasoning,
                "source":    "llm",
                "signals": {
                    "text_match":     confidence,
                    "role_match":     1.0 if ref.startswith("role=") else 0.5,
                    "visibility":     1.0,
                    "uniqueness":     0.7,
                    "proximity":      0.5,
                    "memory_history": 0.0,
                },
            },
        )
    ]
