"""
bubblegum/core/vision/backends/anthropic.py
============================================
Claude (Anthropic) vision backend for element grounding from screenshots.

Given a screenshot and a natural-language instruction, asks a Claude vision
model to locate the matching on-screen elements and return them as structured
candidates (label, role, text, bbox, confidence). Claude's high-resolution
vision returns coordinates that map 1:1 to image pixels, which is exactly what
element grounding needs — no scale-factor math.

Design mirrors OpenAIVisionProvider:
  - inject a preconfigured client (testable without a real API key), or
  - lazily construct `anthropic.Anthropic()` when `create_client=True`.
  - all failures are fail-safe and return an empty candidate list, with a
    sanitized diagnostic available via get_last_diagnostic().

Requires: pip install anthropic  (only when create_client=True / no client injected)
API key:  ANTHROPIC_API_KEY environment variable, or pass api_key=.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from bubblegum.core.vision.engine import VisionCandidate, normalize_vision_candidates

_DEFAULT_MODEL = "claude-opus-4-8"

_PROMPT = (
    "You are a UI element grounding assistant for automated testing. "
    "Look at the screenshot and find every element that matches the instruction. "
    "Respond with ONLY a JSON object — no markdown, no prose — of the form:\n"
    '{"candidates": [{"label": "<visible label>", "role": "<button|link|textbox|...>", '
    '"text": "<visible text or null>", "bbox": [x1, y1, x2, y2], "confidence": <0.0-1.0>}]}\n'
    "bbox is the element's pixel bounding box in the image (top-left x1,y1 to "
    "bottom-right x2,y2), or null if unknown. Order candidates best-match first. "
    "If nothing matches, return {\"candidates\": []}.\n\n"
    "Instruction: "
)


class AnthropicVisionProvider:
    """VisionProvider-compatible backend backed by a Claude vision model."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        max_tokens: int = 2048,
        timeout: float = 30.0,
        create_client: bool = False,
    ) -> None:
        model = model.strip()
        if not model:
            raise ValueError("AnthropicVisionProvider model must be a non-empty string.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or float(timeout) <= 0:
            raise ValueError("AnthropicVisionProvider timeout must be a positive number.")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("AnthropicVisionProvider max_tokens must be a positive integer.")
        if client is None and not create_client:
            raise ValueError(
                "AnthropicVisionProvider requires an injected client or create_client=True. "
                "Install and configure the anthropic SDK, or inject a compatible client."
            )
        self._client = client
        self._model = model
        self._api_key = api_key
        self._max_tokens = int(max_tokens)
        self._timeout = float(timeout)
        self.last_diagnostic: dict[str, Any] | None = None

    def get_last_diagnostic(self) -> dict[str, Any] | None:
        """Return last sanitized provider diagnostic, if any."""
        return self.last_diagnostic

    def _set_diagnostic(
        self,
        *,
        code: str,
        stage: str,
        message: str,
        recoverable: bool,
        exception: Exception | None = None,
    ) -> None:
        diagnostic: dict[str, Any] = {
            "provider": "anthropic_vision",
            "code": code,
            "stage": stage,
            "recoverable": recoverable,
            "message": message,
        }
        if exception is not None:
            diagnostic["exception_type"] = type(exception).__name__
        self.last_diagnostic = diagnostic

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except Exception as exc:  # pragma: no cover - exercised via error behavior
            self._set_diagnostic(
                code="client_init_failed",
                stage="client_init",
                message="anthropic SDK is not installed.",
                recoverable=True,
                exception=exc,
            )
            raise RuntimeError(
                "anthropic SDK is not installed. Install the optional dependency "
                "(pip install anthropic) or inject a preconfigured client."
            ) from exc
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def detect_targets(
        self,
        image_bytes: bytes,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> list[VisionCandidate] | list[dict[str, Any]]:
        self.last_diagnostic = None
        if not image_bytes:
            self._set_diagnostic(
                code="empty_image",
                stage="input",
                message="Screenshot bytes were empty; vision request skipped.",
                recoverable=True,
            )
            return []

        try:
            client = self._ensure_client()
        except Exception as exc:
            if self.last_diagnostic is None:
                self._set_diagnostic(
                    code="client_init_failed",
                    stage="client_init",
                    message="Failed to initialize anthropic client.",
                    recoverable=True,
                    exception=exc,
                )
            return []

        try:
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            prompt = _PROMPT + (instruction or "").strip()
            if context:
                prompt = f"{prompt}\nContext: {json.dumps(context, sort_keys=True)}"

            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = _extract_text(response)
            if not text:
                self._set_diagnostic(
                    code="invalid_response",
                    stage="parse",
                    message="Vision response did not contain parseable text output.",
                    recoverable=True,
                )
                return []
            try:
                parsed = json.loads(_strip_code_fence(text))
            except json.JSONDecodeError as exc:
                self._set_diagnostic(
                    code="parse_failed",
                    stage="parse",
                    message="Vision response JSON parsing failed.",
                    recoverable=True,
                    exception=exc,
                )
                return []
            raw_candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
            return normalize_vision_candidates(raw_candidates)
        except Exception as exc:
            self._set_diagnostic(
                code="request_failed",
                stage="request",
                message="Vision provider request failed.",
                recoverable=True,
                exception=exc,
            )
            return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(response: Any) -> str | None:
    """Pull text from the first text content block in a Messages response."""
    if isinstance(response, str):
        text = response.strip()
        return text or None
    content = getattr(response, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            text = (getattr(block, "text", "") or "").strip()
            if text:
                return text
        elif isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text", "")).strip()
            if text:
                return text
    return None


# Re-export the shared implementation so this module's callers (and tests that
# import it) keep working while there is a single source of truth.
from bubblegum.core.models._shared import strip_code_fence as _strip_code_fence  # noqa: E402
