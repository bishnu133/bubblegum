"""
bubblegum/core/grounding/resolvers/llm_grounding.py
=====================================================
LLMGroundingResolver — Tier 3, priority 50, web + mobile, cost_level=medium.

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

from bubblegum.core import cost, llm_cache
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

# Guaranteed-schema contract for providers that support structured output /
# tool-use. Mirrors the JSON shape described in _SYSTEM_PROMPT so the plain-JSON
# path (older/local models) and the structured path produce identical results.
_GROUNDING_SCHEMA: dict = {
    "name": "ground_element",
    "description": "The single best-matching UI element for the test instruction.",
    "schema": {
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Playwright locator, e.g. role=button[name=\"Save\"] or text=Save. Empty if no match.",
            },
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "required": ["ref", "confidence", "reasoning"],
        "additionalProperties": False,
    },
}


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
    # Text grounding sends only a *filtered* a11y subtree (not screenshots), so
    # it is materially cheaper than vision — classified "medium" so the AI
    # fallback is reachable under the default max_cost_level="medium" policy.
    # Vision/OCR-image resolvers remain "high". The tier still stays dormant
    # until a provider is wired (ai.model set), so there is no surprise spend.
    cost_level: str       = "medium"
    tier:       int       = 3

    def __init__(
        self,
        provider: ModelProvider | None = None,
        *,
        strong_provider: ModelProvider | None = None,
        escalate_below: float = 0.0,
    ) -> None:
        self._provider = provider
        self._strong_provider = strong_provider
        self._escalate_below = float(escalate_below)

    def set_provider(
        self,
        provider: ModelProvider | None,
        *,
        strong: ModelProvider | None = None,
        escalate_below: float = 0.0,
    ) -> None:
        """Inject (or clear) the model provider(s) at runtime.

        The registry constructs this resolver with no provider (stub mode); the
        SDK calls this once the runtime config resolves a usable provider so the
        AI grounding tier goes live. Clearing (``None``) restores stub mode.

        Args:
            provider:       the fast model used for grounding.
            strong:         optional escalation model, tried once when the fast
                            model resolves below ``escalate_below``.
            escalate_below: confidence threshold under which escalation fires
                            (0.0 disables escalation).
        """
        self._provider = provider
        self._strong_provider = strong
        self._escalate_below = float(escalate_below)

    @property
    def has_provider(self) -> bool:
        """True when a model provider is wired — i.e. the AI tier can run."""
        return self._provider is not None

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

        # X2: replay a cached decision for a repeat screen/step — zero model call.
        cache_key = llm_cache.make_key(intent)
        cached = llm_cache.get(cache_key)
        if cached is not None:
            logger.debug("LLMGroundingResolver: cache hit — replaying decision (no model call)")
            return cached

        prompt = _build_prompt(intent.instruction, filtered)

        targets = await self._call_and_parse(self._provider, prompt, intent)

        # Escalation: when the fast model is unsure (empty or below the
        # escalate_below threshold) and a stronger model is wired, try once more
        # with the stronger model and keep whichever result is more confident.
        if self._strong_provider is not None and self._escalate_below > 0.0:
            best = max((t.confidence for t in targets), default=0.0)
            if best < self._escalate_below:
                logger.debug(
                    "LLMGroundingResolver escalating (fast best=%.2f < %.2f) to model=%s",
                    best, self._escalate_below, self._strong_provider.model,
                )
                strong_targets = await self._call_and_parse(self._strong_provider, prompt, intent)
                strong_best = max((t.confidence for t in strong_targets), default=0.0)
                if strong_best > best:
                    targets = strong_targets

        llm_cache.put(cache_key, targets)
        return targets

    async def _call_and_parse(self, provider, prompt: str, intent: StepIntent) -> list[ResolvedTarget]:
        """One model call → parsed targets. Records spend; never raises."""
        logger.debug(
            "LLMGroundingResolver calling provider=%s model=%s action=%s",
            provider.provider_name, provider.model, intent.action_type,
        )
        try:
            result = await provider.complete(
                prompt,
                system=_SYSTEM_PROMPT,
                response_format="json",
                json_schema=_GROUNDING_SCHEMA,
            )
        except Exception as exc:
            logger.error("LLMGroundingResolver provider call failed: %s", exc)
            return []

        # X2: account for the spend (token counts → estimated USD) so the
        # per-run budget can hard-stop further Tier-3 calls.
        try:
            cost.record_usage(
                getattr(result, "model", None) or provider.model,
                getattr(result, "input_tokens", 0),
                getattr(result, "output_tokens", 0),
            )
        except Exception:  # noqa: BLE001 — accounting must never break resolution
            pass

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
